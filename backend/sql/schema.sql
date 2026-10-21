-- Best Carpark App — MySQL 8.0 schema draft (Person A)
-- Convention: all DATETIME values stored in Singapore local time (UTC+8, no DST).
-- Lot type is a column, not a table (Lab 2 TA feedback: fold LotType into Carpark details).

-- ---------------------------------------------------------------
-- 1. Carparks (static info from HDB / URA / LTA / manual)
-- ---------------------------------------------------------------
CREATE TABLE carparks (
    carpark_id        VARCHAR(32)   PRIMARY KEY,          -- internal ID, e.g. 'HDB:ACB', 'URA:A0004'
    name              VARCHAR(255)  NOT NULL,
    address           VARCHAR(255)  NULL,
    latitude          DECIMAL(9,6)  NOT NULL,             -- WGS84 (HDB data is SVY21: convert on import)
    longitude         DECIMAL(9,6)  NOT NULL,
    carpark_type      VARCHAR(32)   NULL,                 -- normalised enum, e.g. MULTI_STOREY, SURFACE, BASEMENT
    parking_system    VARCHAR(32)   NULL,                 -- ELECTRONIC, COUPON
    operator          VARCHAR(64)   NULL,
    gantry_height_m   DECIMAL(4,2)  NULL,
    free_parking      VARCHAR(32)   NULL,                 -- normalised enum, e.g. NO, SUN_PUBLIC_HOLIDAY
    night_parking     BOOLEAN       NULL,
    short_term_parking VARCHAR(32)  NULL,                 -- WHOLE_DAY, NO (season only), or hours e.g. 7AM_10_30PM; NULL = unknown
    has_ev_charging   BOOLEAN       NULL,                 -- NULL = unknown (filled by Person D's matching)
    rate_scheme_id    INT           NULL,                 -- NULL = no reliable pricing -> fee shown as null
    updated_at        DATETIME      NOT NULL,
    INDEX idx_location (latitude, longitude)              -- bounding-box prefilter before 1 km distance check
);

-- One carpark can appear in several sources under different IDs
-- (e.g. an HDB carpark also in LTA DataMall). The poller maps source IDs -> carpark_id here.
CREATE TABLE carpark_source_ids (
    source            ENUM('HDB','URA','LTA','MANUAL') NOT NULL,
    source_ref        VARCHAR(64)   NOT NULL,             -- car_park_no / ppCode / CarParkID
    carpark_id        VARCHAR(32)   NOT NULL,
    PRIMARY KEY (source, source_ref),
    FOREIGN KEY (carpark_id) REFERENCES carparks(carpark_id)
);

-- ---------------------------------------------------------------
-- 2. Parking rates
--    Rules belong to a scheme so many carparks can share one
--    (e.g. all non-central HDB carparks), instead of copying rows.
-- ---------------------------------------------------------------
CREATE TABLE rate_schemes (
    rate_scheme_id    INT           AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(64)   NOT NULL UNIQUE,      -- e.g. 'HDB_NON_CENTRAL', 'HDB_CENTRAL', 'MALL_X'
    source            ENUM('API','MANUAL') NOT NULL,
    effective_from    DATE          NULL,
    notes             VARCHAR(255)  NULL
);

ALTER TABLE carparks
    ADD FOREIGN KEY (rate_scheme_id) REFERENCES rate_schemes(rate_scheme_id);

CREATE TABLE rate_rules (
    rule_id           INT           AUTO_INCREMENT PRIMARY KEY,
    rate_scheme_id    INT           NOT NULL,
    lot_type          ENUM('CAR','MOTORCYCLE','HEAVY_VEHICLE') NOT NULL,
    day_type          ENUM('WEEKDAY','SATURDAY','SUNDAY_PH','ALL') NOT NULL,
    start_time        TIME          NOT NULL,
    end_time          TIME          NOT NULL,             -- end_time <= start_time means the window crosses midnight
    charge_mode       ENUM('PER_INTERVAL','PER_ENTRY','FREE') NOT NULL,
    rate_sgd          DECIMAL(6,2)  NOT NULL DEFAULT 0,   -- per interval, or flat per entry
    interval_min      INT           NULL,                 -- required when PER_INTERVAL
    per_minute        BOOLEAN       NOT NULL DEFAULT FALSE, -- TRUE = prorated per minute (HDB EPS), FALSE = whole intervals (coupon)
    first_interval_min INT          NULL,                 -- e.g. different rate for first hour
    first_rate_sgd    DECIMAL(6,2)  NULL,
    cap_sgd           DECIMAL(6,2)  NULL,
    cap_scope         ENUM('WINDOW','ENTRY','DAY') NULL,  -- what the cap applies to
    grace_min         INT           NULL,
    priority          INT           NOT NULL DEFAULT 0,   -- higher wins when windows overlap
    FOREIGN KEY (rate_scheme_id) REFERENCES rate_schemes(rate_scheme_id),
    INDEX idx_lookup (rate_scheme_id, lot_type, day_type),
    CHECK (charge_mode <> 'PER_INTERVAL' OR interval_min IS NOT NULL),
    CHECK ((cap_sgd IS NULL) = (cap_scope IS NULL))
);

-- ---------------------------------------------------------------
-- 3. Availability
-- ---------------------------------------------------------------
-- Raw history written by the poller (UC-13). Read by Person D for busyness.
CREATE TABLE availability_history (
    id                BIGINT        AUTO_INCREMENT PRIMARY KEY,
    carpark_id        VARCHAR(32)   NOT NULL,
    lot_type          ENUM('CAR','MOTORCYCLE','HEAVY_VEHICLE') NOT NULL,
    available_lots    INT           NOT NULL,
    total_lots        INT           NULL,                 -- NULL when the source gives no total (e.g. LTA)
    observed_at       DATETIME      NOT NULL,             -- the source's own update timestamp
    collected_at      DATETIME      NOT NULL,             -- when our poller fetched it
    day_of_week       TINYINT       AS (DAYOFWEEK(observed_at)) STORED,               -- 1=Sun..7=Sat
    slot_15m          SMALLINT      AS (HOUR(observed_at) * 4 + MINUTE(observed_at) DIV 15) STORED, -- 0..95
    FOREIGN KEY (carpark_id) REFERENCES carparks(carpark_id),
    UNIQUE KEY uq_obs (carpark_id, lot_type, observed_at),  -- INSERT IGNORE skips unchanged readings
    INDEX idx_busyness (carpark_id, lot_type, day_of_week, slot_15m)
);

-- Latest reading per carpark, upserted every poll.
-- Search can read "live" availability from here instead of calling the external API per request.
CREATE TABLE availability_latest (
    carpark_id        VARCHAR(32)   NOT NULL,
    lot_type          ENUM('CAR','MOTORCYCLE','HEAVY_VEHICLE') NOT NULL,
    available_lots    INT           NOT NULL,
    total_lots        INT           NULL,
    observed_at       DATETIME      NOT NULL,
    collected_at      DATETIME      NOT NULL,
    PRIMARY KEY (carpark_id, lot_type),
    FOREIGN KEY (carpark_id) REFERENCES carparks(carpark_id)
);

-- Poller health: lets the app tell "source down" apart from "carpark has no data".
CREATE TABLE collection_runs (
    run_id            BIGINT        AUTO_INCREMENT PRIMARY KEY,
    source            ENUM('HDB','URA','LTA') NOT NULL,
    started_at        DATETIME      NOT NULL,
    finished_at       DATETIME      NULL,
    status            ENUM('OK','FAILED','PARTIAL') NOT NULL,
    rows_inserted     INT           NOT NULL DEFAULT 0,
    error_message     VARCHAR(500)  NULL
);
