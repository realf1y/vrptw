-- ---------------------------------------------------------------------------
-- 带时间窗配送路径优化系统 · 数据库脚本（MySQL 8/9）
-- 数据来源：SQLite D:\vrptw\vrptw.db
-- 执行方式：mysql -u root -p < mysql_vrptw.sql
--           或在 Navicat / MySQL Workbench 中打开本文件整体执行
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS `vrptw` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `vrptw`;

DROP VIEW  IF EXISTS kpi_view;
DROP TABLE IF EXISTS solution;
DROP TABLE IF EXISTS experiment;
DROP TABLE IF EXISTS scene;
DROP TABLE IF EXISTS instance;

CREATE TABLE instance (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(64)  NOT NULL UNIQUE  COMMENT '算例名（如 C101）',
  size          VARCHAR(16)                   COMMENT '规模 25/50/100',
  n_customers   INT          NOT NULL         COMMENT '客户数',
  capacity      DOUBLE       NOT NULL         COMMENT '车辆载重上限',
  vehicle_count INT                           COMMENT '车辆数上限',
  speed         DOUBLE       NOT NULL DEFAULT 1.0 COMMENT '车速：行驶时间=距离/车速',
  total_demand  DOUBLE                        COMMENT '总需求',
  source_path   VARCHAR(255)                  COMMENT '算例文件路径',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='算例';

CREATE TABLE scene (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(64) NOT NULL UNIQUE     COMMENT '场景名',
  config_json TEXT        NOT NULL            COMMENT '场景配置 JSON',
  note        VARCHAR(255)                    COMMENT '说明',
  created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='业务场景配置';

CREATE TABLE experiment (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  instance_id  INT NOT NULL                   COMMENT '算例',
  scene_id     INT NULL                       COMMENT '场景（可空）',
  method       VARCHAR(64) NOT NULL           COMMENT '方法：最近邻/L0/L1/L2/L3',
  run_index    INT NOT NULL                   COMMENT '第几次运行',
  seed         INT NULL                       COMMENT '随机种子',
  iterations   INT NULL                       COMMENT '迭代代数',
  distance     DOUBLE                         COMMENT '总里程',
  vehicles     INT                            COMMENT '车辆数',
  feasible     TINYINT(1)                     COMMENT '是否可行',
  tw_violation DOUBLE                         COMMENT '时间窗违反量',
  on_time_rate DOUBLE                         COMMENT '准时率',
  load_rate    DOUBLE                         COMMENT '装载率',
  seconds      DOUBLE                         COMMENT '求解耗时（秒）',
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_exp_instance FOREIGN KEY (instance_id) REFERENCES instance(id) ON DELETE CASCADE,
  CONSTRAINT fk_exp_scene    FOREIGN KEY (scene_id)    REFERENCES scene(id),
  INDEX idx_exp_instance (instance_id),
  INDEX idx_exp_method   (method)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='实验记录';

CREATE TABLE solution (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  experiment_id INT NOT NULL                  COMMENT '所属实验',
  route_index   INT NOT NULL                  COMMENT '第几条路线',
  customers     TEXT NOT NULL                 COMMENT '客户访问顺序（逗号分隔）',
  stop_count    INT NOT NULL                  COMMENT '停靠点数量',
  route_length  DOUBLE                        COMMENT '该路线里程',
  route_load    DOUBLE                        COMMENT '该路线载重',
  CONSTRAINT fk_sol_exp FOREIGN KEY (experiment_id) REFERENCES experiment(id) ON DELETE CASCADE,
  INDEX idx_sol_exp (experiment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='方案路线';

CREATE OR REPLACE VIEW kpi_view AS
SELECT i.name                        AS instance, i.size AS size, e.method AS method,
       COUNT(*)                      AS runs,
       ROUND(AVG(e.distance), 2)     AS avg_distance,
       ROUND(MIN(e.distance), 2)     AS best_distance,
       ROUND(AVG(e.vehicles), 2)     AS avg_vehicles,
       ROUND(AVG(e.on_time_rate), 4) AS avg_on_time,
       ROUND(AVG(e.load_rate), 4)    AS avg_load_rate,
       ROUND(AVG(e.seconds), 2)      AS avg_seconds
FROM experiment e JOIN instance i ON i.id = e.instance_id
GROUP BY i.name, i.size, e.method;


-- ------------------------------- 数据 -------------------------------

-- instance：3 行
INSERT INTO instance (id, name, size, n_customers, capacity, vehicle_count, speed, total_demand, source_path, created_at) VALUES (1, 'C101', '100', 100, 200.0, 25, 1.0, 1810.0, 'D:\\vrptw\\data\\solomon\\100\\c101.txt', '2026-10-12 05:47:07');
INSERT INTO instance (id, name, size, n_customers, capacity, vehicle_count, speed, total_demand, source_path, created_at) VALUES (2, 'R101', '100', 100, 200.0, 25, 1.0, 1458.0, 'D:\\vrptw\\data\\solomon\\100\\r101.txt', '2026-10-12 05:47:07');
INSERT INTO instance (id, name, size, n_customers, capacity, vehicle_count, speed, total_demand, source_path, created_at) VALUES (3, 'RC101', '100', 100, 200.0, 25, 1.0, 1724.0, 'D:\\vrptw\\data\\solomon\\100\\rc101.txt', '2026-10-12 05:47:07');

-- scene：3 行
INSERT INTO scene (id, name, config_json, note, created_at) VALUES (1, '标准场景-硬时间窗', '{"name": "标准场景-硬时间窗", "instance": "data/solomon/100/c101.txt", "capacity": null, "max_vehicles": null, "speed": 1.0, "tw_mode": "hard", "lambda_tw": 10.0, "priority": {}, "aco": {}, "note": "完全按算例原始约束：硬时间窗、车速 1.0"}', '完全按算例原始约束：硬时间窗、车速 1.0', '2026-10-12 05:56:08');
INSERT INTO scene (id, name, config_json, note, created_at) VALUES (2, '校园配送-软时间窗', '{"name": "校园配送-软时间窗", "instance": "data/solomon/100/c101.txt", "capacity": null, "max_vehicles": null, "speed": 1.0, "tw_mode": "soft", "lambda_tw": 25.0, "priority": {}, "aco": {}, "note": "允许小幅迟到，按 λ 罚分；适合业务上“晚到可接受但要付出代价”的场景"}', '允许小幅迟到，按 λ 罚分；适合业务上“晚到可接受但要付出代价”的场景', '2026-10-12 05:56:08');
INSERT INTO scene (id, name, config_json, note, created_at) VALUES (3, '雨天慢速-软时间窗', '{"name": "雨天慢速-软时间窗", "instance": "data/solomon/100/c101.txt", "capacity": null, "max_vehicles": null, "speed": 0.8, "tw_mode": "soft", "lambda_tw": 50.0, "priority": {}, "aco": {}, "note": "雨天路滑导致车速降为 0.8，迟到代价加倍"}', '雨天路滑导致车速降为 0.8，迟到代价加倍', '2026-10-12 05:56:08');

-- experiment：46 行
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (1, 1, NULL, '最近邻(贪心)', 2, NULL, NULL, 1870.73, 21, 1, 0.0, 1.0, 0.431, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (2, 1, NULL, '最近邻(贪心)', 1, NULL, NULL, 1870.73, 21, 1, 0.0, 1.0, 0.431, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (3, 1, NULL, '最近邻(贪心)', 3, NULL, NULL, 1870.73, 21, 1, 0.0, 1.0, 0.431, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (4, 2, NULL, '最近邻(贪心)', 1, NULL, NULL, 2623.26, 37, 1, 0.0, 1.0, 0.197, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (5, 2, NULL, '最近邻(贪心)', 2, NULL, NULL, 2623.26, 37, 1, 0.0, 1.0, 0.197, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (6, 2, NULL, '最近邻(贪心)', 3, NULL, NULL, 2623.26, 37, 1, 0.0, 1.0, 0.197, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (7, 3, NULL, '最近邻(贪心)', 1, NULL, NULL, 2711.29, 27, 1, 0.0, 1.0, 0.3193, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (8, 3, NULL, '最近邻(贪心)', 2, NULL, NULL, 2711.29, 27, 1, 0.0, 1.0, 0.3193, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (9, 3, NULL, '最近邻(贪心)', 3, NULL, NULL, 2711.29, 27, 1, 0.0, 1.0, 0.3193, 0.0, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (10, 1, NULL, 'L1 +时间窗η', 3, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 1.53, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (11, 1, NULL, 'L1 +时间窗η', 1, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 1.56, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (12, 1, NULL, 'L2 +MMAS精英', 3, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 1.58, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (13, 1, NULL, 'L1 +时间窗η', 2, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 1.6, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (14, 1, NULL, 'L2 +MMAS精英', 1, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 1.6, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (15, 1, NULL, 'L2 +MMAS精英', 2, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 1.63, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (16, 1, NULL, 'L0 基线ACO', 3, NULL, NULL, 1781.49, 20, 1, 0.0, 1.0, 0.4525, 1.66, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (17, 1, NULL, 'L0 基线ACO', 1, NULL, NULL, 1951.13, 24, 1, 0.0, 1.0, 0.3771, 1.69, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (18, 2, NULL, 'L2 +MMAS精英', 3, NULL, NULL, 2192.92, 25, 1, 0.0, 1.0, 0.2916, 1.65, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (19, 2, NULL, 'L1 +时间窗η', 2, NULL, NULL, 2234.32, 25, 1, 0.0, 1.0, 0.2916, 1.71, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (20, 3, NULL, 'L1 +时间窗η', 2, NULL, NULL, 2300.27, 19, 1, 0.0, 1.0, 0.4537, 1.64, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (21, 3, NULL, 'L1 +时间窗η', 3, NULL, NULL, 2331.71, 21, 1, 0.0, 1.0, 0.4105, 1.65, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (22, 2, NULL, 'L1 +时间窗η', 1, NULL, NULL, 2204.26, 24, 1, 0.0, 1.0, 0.3038, 1.75, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (23, 2, NULL, 'L2 +MMAS精英', 2, NULL, NULL, 2184.99, 24, 1, 0.0, 1.0, 0.3038, 1.72, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (24, 1, NULL, 'L0 基线ACO', 2, NULL, NULL, 1907.91, 23, 1, 0.0, 1.0, 0.3935, 1.8, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (25, 3, NULL, 'L1 +时间窗η', 1, NULL, NULL, 2267.1, 20, 1, 0.0, 1.0, 0.431, 1.67, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (26, 2, NULL, 'L1 +时间窗η', 3, NULL, NULL, 2188.21, 23, 1, 0.0, 1.0, 0.317, 1.74, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (27, 2, NULL, 'L2 +MMAS精英', 1, NULL, NULL, 2130.55, 24, 1, 0.0, 1.0, 0.3038, 1.75, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (28, 2, NULL, 'L0 基线ACO', 2, NULL, NULL, 2511.85, 35, 1, 0.0, 1.0, 0.2083, 1.83, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (29, 3, NULL, 'L0 基线ACO', 2, NULL, NULL, 2694.58, 27, 1, 0.0, 1.0, 0.3193, 1.75, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (30, 3, NULL, 'L0 基线ACO', 3, NULL, NULL, 2657.16, 27, 1, 0.0, 1.0, 0.3193, 1.77, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (31, 3, NULL, 'L0 基线ACO', 1, NULL, NULL, 2502.95, 26, 1, 0.0, 1.0, 0.3315, 1.77, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (32, 2, NULL, 'L0 基线ACO', 3, NULL, NULL, 2580.68, 36, 1, 0.0, 1.0, 0.2025, 1.92, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (33, 2, NULL, 'L0 基线ACO', 1, NULL, NULL, 2577.88, 33, 1, 0.0, 1.0, 0.2209, 1.92, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (34, 3, NULL, 'L2 +MMAS精英', 2, NULL, NULL, 2198.64, 19, 1, 0.0, 1.0, 0.4537, 1.17, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (35, 3, NULL, 'L2 +MMAS精英', 1, NULL, NULL, 2181.01, 20, 1, 0.0, 1.0, 0.431, 1.21, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (36, 3, NULL, 'L2 +MMAS精英', 3, NULL, NULL, 2207.61, 20, 1, 0.0, 1.0, 0.431, 1.23, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (37, 1, NULL, 'L3 +局部搜索(改进版)', 1, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 6.08, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (38, 1, NULL, 'L3 +局部搜索(改进版)', 3, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 6.38, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (39, 1, NULL, 'L3 +局部搜索(改进版)', 2, NULL, NULL, 829.01, 10, 1, 0.0, 1.0, 0.905, 7.52, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (40, 2, NULL, 'L3 +局部搜索(改进版)', 2, NULL, NULL, 1953.3, 24, 1, 0.0, 1.0, 0.3038, 9.24, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (41, 2, NULL, 'L3 +局部搜索(改进版)', 3, NULL, NULL, 2025.49, 23, 1, 0.0, 1.0, 0.317, 9.57, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (42, 2, NULL, 'L3 +局部搜索(改进版)', 1, NULL, NULL, 2027.6, 23, 0, 0.12, 0.99, 0.317, 9.65, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (43, 3, NULL, 'L3 +局部搜索(改进版)', 1, NULL, NULL, 2120.57, 20, 1, 0.0, 1.0, 0.431, 10.86, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (44, 3, NULL, 'L3 +局部搜索(改进版)', 3, NULL, NULL, 2120.62, 21, 1, 0.0, 1.0, 0.4105, 11.27, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (45, 3, NULL, 'L3 +局部搜索(改进版)', 2, NULL, NULL, 2097.53, 20, 0, 0.1, 0.99, 0.431, 11.33, '2026-10-12 05:47:07');
INSERT INTO experiment (id, instance_id, scene_id, method, run_index, seed, iterations, distance, vehicles, feasible, tw_violation, on_time_rate, load_rate, seconds, created_at) VALUES (46, 1, NULL, 'L3 +局部搜索(改进版)', 1, 1, 20, 829.01, 10, 1, 0.0, 1.0, 0.905, 2.77, '2026-10-12 05:47:10');

-- solution：10 行
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (1, 46, 1, '67,65,63,62,74,72,61,64,68,66,69', 11, 59.41, 200.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (2, 46, 2, '5,3,7,8,10,11,9,6,4,2,1,75', 12, 59.63, 180.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (3, 46, 3, '43,42,41,40,44,46,45,48,51,50,52,49,47', 13, 64.81, 160.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (4, 46, 4, '20,24,25,27,29,30,28,26,23,22,21', 11, 50.81, 170.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (5, 46, 5, '81,78,76,71,70,73,77,79,80', 9, 127.3, 150.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (6, 46, 6, '90,87,86,83,82,84,85,88,89,91', 10, 76.08, 170.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (7, 46, 7, '57,55,54,53,56,58,60,59', 8, 101.89, 200.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (8, 46, 8, '13,17,18,19,15,16,14,12', 8, 95.89, 190.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (9, 46, 9, '32,33,31,35,37,38,39,36,34', 9, 97.23, 200.0);
INSERT INTO solution (id, experiment_id, route_index, customers, stop_count, route_length, route_load) VALUES (10, 46, 10, '98,96,95,94,92,93,97,100,99', 9, 95.96, 190.0);
