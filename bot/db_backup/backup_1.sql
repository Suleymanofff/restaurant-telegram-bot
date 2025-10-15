-- =============================================
-- BACKUP SCRIPT FOR RESTAURANT BOT DATABASE
-- =============================================

-- Удаляем таблицы в правильном порядке (с учетом внешних ключей)
DROP TABLE IF EXISTS referral_bonuses CASCADE;
DROP TABLE IF EXISTS menu_views CASCADE;
DROP TABLE IF EXISTS user_actions CASCADE;
DROP TABLE IF EXISTS broadcasts CASCADE;
DROP TABLE IF EXISTS staff_calls CASCADE;
DROP TABLE IF EXISTS reservations CASCADE;
DROP TABLE IF EXISTS delivery_orders CASCADE;
DROP TABLE IF EXISTS payment_receipts CASCADE;
DROP TABLE IF EXISTS bonus_transactions CASCADE;
DROP TABLE IF EXISTS admin_users CASCADE;
DROP TABLE IF EXISTS staff_users CASCADE;
DROP TABLE IF EXISTS delivery_menu CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Удаляем функцию обновления updated_at
DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;

-- =============================================
-- СОЗДАНИЕ ТАБЛИЦ
-- =============================================

-- Таблица пользователей (с реферальными полями и балансом)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    full_name VARCHAR(255) NOT NULL,
    sex VARCHAR(10) CHECK (sex IN ('male', 'female', 'other', 'unknown')),
    major VARCHAR(50) CHECK (major IN ('student', 'entrepreneur', 'hire', 'frilans', 'other', 'unknown')),
    language_code VARCHAR(10) DEFAULT 'ru',
    is_blocked BOOLEAN DEFAULT FALSE,
    
    -- Реферальные поля
    referrer_id BIGINT,
    referral_code VARCHAR(20) UNIQUE,
    referral_count INTEGER DEFAULT 0,
    total_referral_bonus DECIMAL(10,2) DEFAULT 0,
    
    -- Личный счет пользователя
    bonus_balance DECIMAL(10,2) DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (referrer_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- Таблица администраторов
CREATE TABLE admin_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    full_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Таблица официантов  
CREATE TABLE staff_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    full_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Таблица реферальных бонусов
CREATE TABLE referral_bonuses (
    id SERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    referred_id BIGINT NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    bonus_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled')),
    order_id INTEGER, -- ID заказа, за который начислен бонус
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Таблица бронирований
CREATE TABLE reservations (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    reservation_date DATE NOT NULL,
    reservation_time TIME NOT NULL,
    guests_count INTEGER NOT NULL CHECK (guests_count > 0 AND guests_count <= 20),
    customer_name VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed')),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Таблица вызовов персонала
CREATE TABLE staff_calls (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    table_number INTEGER NOT NULL CHECK (table_number > 0 AND table_number <= 99),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'completed', 'cancelled')),
    notes TEXT,
    accepted_by_name VARCHAR(255),  -- Имя официанта
    accepted_by BIGINT,             -- ID официанта
    message_ids JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    accepted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE
);

-- Таблица рассылок
CREATE TABLE broadcasts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    message_text TEXT NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text',
    image_file_id VARCHAR(500),
    buttons JSONB,
    target_sex VARCHAR(10) CHECK (target_sex IN ('male', 'female', 'all')),
    target_major VARCHAR(50) CHECK (target_major IN ('student', 'entrepreneur', 'hire', 'frilans', 'all')),
    sent_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    read_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'sending', 'completed', 'cancelled')),
    scheduled_at TIMESTAMP WITH TIME ZONE,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Таблица действий пользователей
CREATE TABLE user_actions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL,
    action_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Таблица просмотров меню
CREATE TABLE menu_views (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    view_count INTEGER DEFAULT 1,
    last_viewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, category)
);

-- Таблица заказов доставки (добавляем поля для скидок и бонусов)
CREATE TABLE delivery_orders (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    order_data JSONB NOT NULL,

    -- Основная информация о статусе
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'preparing', 'on_way', 'delivered', 'cancelled')),
    priority INTEGER DEFAULT 1 CHECK (priority IN (1, 2, 3)), -- 1=normal, 2=medium, 3=high

    -- Информация о клиенте (дублируется в order_data для быстрого поиска)
    customer_name VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    delivery_address TEXT NOT NULL,
    delivery_time TEXT, -- Предпочтительное время доставки
    customer_notes TEXT, -- Пожелания клиента

    -- ПОЛЯ ДЛЯ ОПЛАТЫ
    payment_method VARCHAR(20) DEFAULT 'cash' CHECK (payment_method IN ('cash','card','bank_transfer')),
    payment_status VARCHAR(20) DEFAULT 'pending' CHECK (payment_status IN ('pending','confirmed','rejected')),
    payment_notes TEXT,
    payment_transaction_id TEXT, -- внешний ID платежа / reference from provider
    payment_attempts INTEGER DEFAULT 0, -- количество попыток оплаты/прикрепления квитанций

    -- audit поля для подтверждения/отклонения платежа
    payment_confirmed_by BIGINT, -- admin id
    payment_confirmed_at TIMESTAMP WITH TIME ZONE,
    payment_rejected_by BIGINT,
    payment_rejected_at TIMESTAMP WITH TIME ZONE,
    payment_reject_reason TEXT,

    -- Финансовая информация
    total_amount DECIMAL(10,2) NOT NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0, -- Скидка по реферальной программе
    bonus_used DECIMAL(10,2) DEFAULT 0, -- Использовано бонусов
    final_amount DECIMAL(10,2) NOT NULL, -- Итоговая сумма к оплате

    -- Назначение ответственных
    assigned_cook BIGINT, -- ID повара (ссылка на users)
    assigned_courier BIGINT, -- ID курьера (ссылка на users)

    -- Временные метки и расчёты
    estimated_delivery_time INTEGER, -- Предполагаемое время доставки в минутах
    preparation_time INTEGER, -- Время приготовления в минутах
    actual_delivery_time TIMESTAMP WITH TIME ZONE, -- Фактическое время доставки

    -- Системные поля
    delivery_notes TEXT, -- Внутренние заметки для курьера/повара
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


-- New table for receipts
CREATE TABLE IF NOT EXISTS payment_receipts (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES delivery_orders(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    file_id TEXT NOT NULL, -- file_id Telegram
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Таблица элементов меню доставки
CREATE TABLE delivery_menu (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    image_url VARCHAR(500),
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Таблица для бонусных транзакций
CREATE TABLE bonus_transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    order_id INTEGER REFERENCES delivery_orders(id) ON DELETE SET NULL,
    amount DECIMAL(10,2) NOT NULL, -- положительное = начисление, отрицательное = списание
    type VARCHAR(50) NOT NULL, -- 'cashback', 'purchase', 'referral', 'manual'
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ
-- =============================================

-- Индексы для users
CREATE INDEX idx_users_user_id ON users(user_id);
CREATE INDEX idx_users_sex ON users(sex);
CREATE INDEX idx_users_major ON users(major);
CREATE INDEX idx_users_created_at ON users(created_at);
CREATE INDEX idx_users_blocked ON users(is_blocked);
CREATE INDEX idx_users_referral_code ON users(referral_code);
CREATE INDEX idx_users_referrer_id ON users(referrer_id);

-- Индексы для bonus_transactions
CREATE INDEX idx_bonus_transactions_user_id ON bonus_transactions(user_id);
CREATE INDEX idx_bonus_transactions_created ON bonus_transactions(created_at);
CREATE INDEX idx_bonus_transactions_type ON bonus_transactions(type);

-- Индексы для referral_bonuses
CREATE INDEX idx_referral_bonuses_referrer ON referral_bonuses(referrer_id);
CREATE INDEX idx_referral_bonuses_referred ON referral_bonuses(referred_id);
CREATE INDEX idx_referral_bonuses_status ON referral_bonuses(status);

-- Индексы для reservations
CREATE INDEX idx_reservations_user_id ON reservations(user_id);
CREATE INDEX idx_reservations_date ON reservations(reservation_date);
CREATE INDEX idx_reservations_status ON reservations(status);
CREATE INDEX idx_reservations_created_at ON reservations(created_at);

-- Индексы для staff_calls
CREATE INDEX idx_staff_calls_status ON staff_calls(status);
CREATE INDEX idx_staff_calls_created ON staff_calls(created_at);
CREATE INDEX idx_staff_calls_user ON staff_calls(user_id);
CREATE INDEX idx_staff_calls_table ON staff_calls(table_number);

-- Индексы для user_actions
CREATE INDEX idx_user_actions_user_id ON user_actions(user_id);
CREATE INDEX idx_user_actions_type ON user_actions(action_type);
CREATE INDEX idx_user_actions_created_at ON user_actions(created_at);

-- Индексы для menu_views
CREATE INDEX idx_menu_views_user_id ON menu_views(user_id);
CREATE INDEX idx_menu_views_category ON menu_views(category);

-- Индексы для broadcasts
CREATE INDEX idx_broadcasts_status ON broadcasts(status);
CREATE INDEX idx_broadcasts_scheduled ON broadcasts(scheduled_at);
CREATE INDEX idx_broadcasts_type ON broadcasts(message_type);
CREATE INDEX idx_broadcasts_created ON broadcasts(created_at);

-- Индексы для delivery
CREATE INDEX idx_delivery_orders_status ON delivery_orders(status);
CREATE INDEX idx_delivery_orders_created ON delivery_orders(created_at);
CREATE INDEX idx_delivery_menu_category ON delivery_menu(category);
CREATE INDEX idx_delivery_menu_available ON delivery_menu(is_available);

-- =============================================
-- ТРИГГЕРЫ
-- =============================================

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для users
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Триггер для reservations
CREATE TRIGGER update_reservations_updated_at 
    BEFORE UPDATE ON reservations 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Триггер для updated_at в delivery
CREATE TRIGGER update_delivery_orders_updated_at 
    BEFORE UPDATE ON delivery_orders 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- ТЕСТОВЫЕ ДАННЫЕ
-- =============================================

-- Очищаем последовательности (если нужно сбросить ID)
ALTER SEQUENCE users_id_seq RESTART WITH 1;
ALTER SEQUENCE referral_bonuses_id_seq RESTART WITH 1;
ALTER SEQUENCE reservations_id_seq RESTART WITH 1;
ALTER SEQUENCE staff_calls_id_seq RESTART WITH 1;
ALTER SEQUENCE broadcasts_id_seq RESTART WITH 1;
ALTER SEQUENCE user_actions_id_seq RESTART WITH 1;
ALTER SEQUENCE menu_views_id_seq RESTART WITH 1;
ALTER SEQUENCE delivery_orders_id_seq RESTART WITH 1;
ALTER SEQUENCE delivery_menu_id_seq RESTART WITH 1;

-- Сначала создаем базовых пользователей
INSERT INTO users (user_id, username, full_name, language_code) VALUES
(5170209314, 'admin', 'Администратор', 'ru'),
(7553841581, 'staff', 'Официант', 'ru')
ON CONFLICT (user_id) DO UPDATE SET
    username = EXCLUDED.username,
    full_name = EXCLUDED.full_name,
    language_code = EXCLUDED.language_code;

-- Тестовые данные для меню доставки
INSERT INTO delivery_menu (category, name, description, price) VALUES
('breakfasts', 'Сырники с малиновым соусом', 'Нежные творожные сырники с хрустящей корочкой и свежим ягодным соусом', 450.00),
('breakfasts', 'Авокадо-тост с лососем', 'Хрустящий тост с пюре из авокадо и слабосоленым лососем', 520.00),
('breakfasts', 'Омлет с шампиньонами', 'Пышный омлет с нежными шампиньонами и сыром', 380.00),
('breakfasts', 'Гранола с йогуртом', 'Хрустящая домашняя гранола с греческим йогуртом и ягодами', 420.00),
('breakfasts', 'Блины с кленовым сиропом', 'Тонкие воздушные блины с ароматным кленовым сиропом', 390.00),
('hots', 'Стейк из мраморной говядины', 'Сочный стейк средней прожарки с розмарином и овощами гриль', 1200.00),
('hots', 'Лосось в медово-соевом соусе', 'Нежное филе лосося в пикантном медово-соевом глазури', 890.00),
('hots', 'Утка с апельсиновым соусом', 'Хрустящая утиная грудка с цитрусовым соусом и пюре', 950.00),
('hots', 'Рагу из телятины', 'Ароматное рагу из нежной телятины с сезонными овощами', 680.00),
('hots', 'Куриные медальоны', 'Нежные куриные медальоны в сливочном соусе с грибами', 580.00),
('hot_drinks', 'Эспрессо', 'Классический крепкий эспрессо из арабики', 180.00),
('hot_drinks', 'Капучино', 'Идеальный баланс эспрессо и воздушной молочной пенки', 250.00),
('hot_drinks', 'Латте с сиропом', 'Нежный кофейный напиток с выбором сиропов', 320.00),
('hot_drinks', 'Чай матча', 'Традиционный японский зеленый чай с нежным вкусом', 280.00),
('hot_drinks', 'Горячий шоколад', 'Насыщенный шоколадный напиток со взбитыми сливками', 350.00),
('cold_drinks', 'Мохито', 'Освежающий коктейль с лаймом и мятой', 330.00),
('cold_drinks', 'Фраппе', 'Холодный кофейный коктейль со льдом', 340.00),
('cold_drinks', 'Лимонад ягодный', 'Домашний лимонад со свежими ягодами и мятой', 290.00),
('cold_drinks', 'Смузи тропический', 'Фруктовый смузи с манго, бананом и кокосом', 320.00),
('cold_drinks', 'Айс ти', 'Освежающий холодный чай с лимоном и персиком', 260.00),
('deserts', 'Тирамису', 'Классический итальянский десерт с кофейным вкусом', 480.00),
('deserts', 'Чизкейк Нью-Йорк', 'Нежный чизкейк с ягодным топпингом', 520.00),
('deserts', 'Фондан', 'Шоколадный кекс с текучей начинкой', 450.00),
('deserts', 'Крем-брюле', 'Нежный крем с хрустящей карамельной корочкой', 420.00),
('deserts', 'Яблочный штрудель', 'Тонкое тесто с яблочной начинкой и корицей', 380.00)

ON CONFLICT (id) DO UPDATE SET
    category = EXCLUDED.category,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    price = EXCLUDED.price;

-- Вставляем текущих админов и стафф (после создания пользователей)
INSERT INTO admin_users (user_id, username, full_name) 
VALUES 
(5170209314, 'admin', 'Администратор')
ON CONFLICT (user_id) DO UPDATE SET
    username = EXCLUDED.username,
    full_name = EXCLUDED.full_name;

INSERT INTO staff_users (user_id, username, full_name) 
VALUES 
(5170209314, 'admin', 'Администратор'),
(7553841581, 'staff', 'Официант')
ON CONFLICT (user_id) DO UPDATE SET
    username = EXCLUDED.username,
    full_name = EXCLUDED.full_name;

-- =============================================
-- ПРОВЕРОЧНЫЕ ЗАПРОСЫ
-- =============================================

-- Проверяем количество записей в таблицах
SELECT 'users' as table_name, COUNT(*) as record_count FROM users
UNION ALL
SELECT 'admin_users', COUNT(*) FROM admin_users
UNION ALL
SELECT 'staff_users', COUNT(*) FROM staff_users
UNION ALL
SELECT 'referral_bonuses', COUNT(*) FROM referral_bonuses
UNION ALL
SELECT 'bonus_transactions', COUNT(*) FROM bonus_transactions
UNION ALL
SELECT 'reservations', COUNT(*) FROM reservations
UNION ALL
SELECT 'staff_calls', COUNT(*) FROM staff_calls
UNION ALL
SELECT 'user_actions', COUNT(*) FROM user_actions
UNION ALL
SELECT 'menu_views', COUNT(*) FROM menu_views
UNION ALL
SELECT 'broadcasts', COUNT(*) FROM broadcasts
UNION ALL
SELECT 'delivery_orders', COUNT(*) FROM delivery_orders
UNION ALL
SELECT 'delivery_menu', COUNT(*) FROM delivery_menu;

-- =============================================
-- BACKUP ЗАВЕРШЕН
-- =============================================

SELECT '✅ Database backup completed successfully!' as result;