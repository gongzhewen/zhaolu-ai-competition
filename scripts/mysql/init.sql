CREATE DATABASE IF NOT EXISTS zhaolu_v2
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS zhaolu_sys
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS zhaolu_dim
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS zhaolu_fact
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS zhaolu_gov
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS zhaolu_ai
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS zhaolu_analytics
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'zhaolu_app'@'localhost'
  IDENTIFIED BY 'CHANGE_ME';

GRANT ALL PRIVILEGES ON zhaolu_v2.* TO 'zhaolu_app'@'localhost';
GRANT ALL PRIVILEGES ON zhaolu_sys.* TO 'zhaolu_app'@'localhost';
GRANT ALL PRIVILEGES ON zhaolu_dim.* TO 'zhaolu_app'@'localhost';
GRANT ALL PRIVILEGES ON zhaolu_fact.* TO 'zhaolu_app'@'localhost';
GRANT ALL PRIVILEGES ON zhaolu_gov.* TO 'zhaolu_app'@'localhost';
GRANT ALL PRIVILEGES ON zhaolu_ai.* TO 'zhaolu_app'@'localhost';
GRANT ALL PRIVILEGES ON zhaolu_analytics.* TO 'zhaolu_app'@'localhost';
FLUSH PRIVILEGES;
