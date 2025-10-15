import asyncio
import psutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class HealthCheckResult:
    component: str
    status: HealthStatus
    message: str
    response_time: float
    timestamp: datetime

class HealthMonitor:
    def __init__(self, db_manager, bot):
        self.db_manager = db_manager
        self.bot = bot
        self.health_history: List[HealthCheckResult] = []
        self.max_history_size = 100
        
    async def perform_full_health_check(self) -> Dict[str, Any]:
        """Выполняет полную проверку здоровья системы"""
        checks = [
            self._check_database_connection,
            self._check_database_performance,
            self._check_memory_usage,
            self._check_disk_usage,
            self._check_bot_connection,
            self._check_background_tasks
        ]
        
        results = []
        overall_status = HealthStatus.HEALTHY
        
        for check in checks:
            try:
                result = await check()
                results.append(result)
                
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
                    
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                result = HealthCheckResult(
                    component=check.__name__,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(e)}",
                    response_time=0,
                    timestamp=datetime.now()
                )
                results.append(result)
                overall_status = HealthStatus.UNHEALTHY
        
        # Сохраняем в историю
        self.health_history.extend(results)
        if len(self.health_history) > self.max_history_size:
            self.health_history = self.health_history[-self.max_history_size:]
        
        return {
            "status": overall_status,
            "timestamp": datetime.now(),
            "checks": [self._result_to_dict(r) for r in results],
            "summary": self._generate_summary(results)
        }
    
    async def _check_database_connection(self) -> HealthCheckResult:
        """Проверка соединения с БД"""
        start_time = datetime.now()
        try:
            is_healthy = await self.db_manager.health_check()
            response_time = (datetime.now() - start_time).total_seconds()
            
            if is_healthy:
                return HealthCheckResult(
                    component="database_connection",
                    status=HealthStatus.HEALTHY,
                    message="Database connection is stable",
                    response_time=response_time,
                    timestamp=datetime.now()
                )
            else:
                return HealthCheckResult(
                    component="database_connection",
                    status=HealthStatus.UNHEALTHY,
                    message="Database connection failed",
                    response_time=response_time,
                    timestamp=datetime.now()
                )
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            return HealthCheckResult(
                component="database_connection",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection error: {str(e)}",
                response_time=response_time,
                timestamp=datetime.now()
            )
    
    async def _check_database_performance(self) -> HealthCheckResult:
        """Проверка производительности БД"""
        start_time = datetime.now()
        try:
            async with self.db_manager.pool.acquire() as conn:
                # Проверяем время выполнения простого запроса
                query_start = datetime.now()
                await conn.fetchval("SELECT 1")
                query_time = (datetime.now() - query_start).total_seconds()
                
                # Проверяем количество соединений
                connections = await conn.fetchval("""
                    SELECT count(*) FROM pg_stat_activity 
                    WHERE datname = current_database()
                """)
                
            response_time = (datetime.now() - start_time).total_seconds()
            
            if query_time < 0.1:  # 100ms threshold
                status = HealthStatus.HEALTHY
                message = f"Database performance normal (query: {query_time:.3f}s, connections: {connections})"
            elif query_time < 1.0:
                status = HealthStatus.DEGRADED
                message = f"Database performance degraded (query: {query_time:.3f}s, connections: {connections})"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Database performance critical (query: {query_time:.3f}s, connections: {connections})"
                
            return HealthCheckResult(
                component="database_performance",
                status=status,
                message=message,
                response_time=response_time,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            return HealthCheckResult(
                component="database_performance",
                status=HealthStatus.UNHEALTHY,
                message=f"Database performance check failed: {str(e)}",
                response_time=response_time,
                timestamp=datetime.now()
            )
    
    async def _check_memory_usage(self) -> HealthCheckResult:
        """Проверка использования памяти"""
        try:
            memory = psutil.virtual_memory()
            response_time = 0.001  # Быстрая проверка
            
            if memory.percent < 80:
                status = HealthStatus.HEALTHY
                message = f"Memory usage: {memory.percent:.1f}%"
            elif memory.percent < 90:
                status = HealthStatus.DEGRADED
                message = f"Memory usage high: {memory.percent:.1f}%"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Memory usage critical: {memory.percent:.1f}%"
                
            return HealthCheckResult(
                component="memory_usage",
                status=status,
                message=message,
                response_time=response_time,
                timestamp=datetime.now()
            )
        except Exception as e:
            return HealthCheckResult(
                component="memory_usage",
                status=HealthStatus.DEGRADED,
                message=f"Memory check unavailable: {str(e)}",
                response_time=0,
                timestamp=datetime.now()
            )
    
    async def _check_disk_usage(self) -> HealthCheckResult:
        """Проверка использования диска"""
        try:
            disk = psutil.disk_usage('/')
            response_time = 0.001
            
            if disk.percent < 85:
                status = HealthStatus.HEALTHY
                message = f"Disk usage: {disk.percent:.1f}%"
            elif disk.percent < 95:
                status = HealthStatus.DEGRADED
                message = f"Disk usage high: {disk.percent:.1f}%"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Disk usage critical: {disk.percent:.1f}%"
                
            return HealthCheckResult(
                component="disk_usage",
                status=status,
                message=message,
                response_time=response_time,
                timestamp=datetime.now()
            )
        except Exception as e:
            return HealthCheckResult(
                component="disk_usage",
                status=HealthStatus.DEGRADED,
                message=f"Disk check unavailable: {str(e)}",
                response_time=0,
                timestamp=datetime.now()
            )
    
    async def _check_bot_connection(self) -> HealthCheckResult:
        """Проверка соединения с Telegram API"""
        start_time = datetime.now()
        try:
            me = await self.bot.get_me()
            response_time = (datetime.now() - start_time).total_seconds()
            
            return HealthCheckResult(
                component="bot_connection",
                status=HealthStatus.HEALTHY,
                message=f"Bot connection OK (@{me.username})",
                response_time=response_time,
                timestamp=datetime.now()
            )
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            return HealthCheckResult(
                component="bot_connection",
                status=HealthStatus.UNHEALTHY,
                message=f"Bot connection failed: {str(e)}",
                response_time=response_time,
                timestamp=datetime.now()
            )
    
    async def _check_background_tasks(self) -> HealthCheckResult:
        """Проверка фоновых задач"""
        try:
            # Здесь можно добавить проверки специфичных фоновых задач
            tasks = asyncio.all_tasks()
            background_count = len([t for t in tasks if not t.done() and "background" in str(t).lower()])
            
            return HealthCheckResult(
                component="background_tasks",
                status=HealthStatus.HEALTHY,
                message=f"Background tasks running: {background_count}",
                response_time=0.001,
                timestamp=datetime.now()
            )
        except Exception as e:
            return HealthCheckResult(
                component="background_tasks",
                status=HealthStatus.DEGRADED,
                message=f"Background tasks check failed: {str(e)}",
                response_time=0,
                timestamp=datetime.now()
            )
    
    def _result_to_dict(self, result: HealthCheckResult) -> Dict[str, Any]:
        """Конвертирует результат в словарь"""
        return {
            "component": result.component,
            "status": result.status.value,
            "message": result.message,
            "response_time": result.response_time,
            "timestamp": result.timestamp.isoformat()
        }
    
    def _generate_summary(self, results: List[HealthCheckResult]) -> Dict[str, Any]:
        """Генерирует сводку по проверкам"""
        total_checks = len(results)
        healthy_checks = len([r for r in results if r.status == HealthStatus.HEALTHY])
        degraded_checks = len([r for r in results if r.status == HealthStatus.DEGRADED])
        unhealthy_checks = len([r for r in results if r.status == HealthStatus.UNHEALTHY])
        
        # Среднее время ответа
        avg_response_time = sum(r.response_time for r in results) / total_checks if total_checks > 0 else 0
        
        return {
            "total_checks": total_checks,
            "healthy_checks": healthy_checks,
            "degraded_checks": degraded_checks,
            "unhealthy_checks": unhealthy_checks,
            "success_rate": (healthy_checks / total_checks) * 100 if total_checks > 0 else 0,
            "avg_response_time": avg_response_time
        }
    
    def get_health_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Возвращает историю проверок здоровья за указанные часы"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_checks = [r for r in self.health_history if r.timestamp > cutoff_time]
        return [self._result_to_dict(r) for r in recent_checks]