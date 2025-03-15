import pyodbc

# Database Connection Configuration
DB_CONFIG = {
    "DRIVER": "{ODBC Driver 17 for SQL Server}",
    "SERVER": "40.121.205.186",
    "DATABASE": "HRVMS_test",
    "UID": "saclient",
    "PWD": "#Client!!#Server@890*"
}

def get_db_connection():
    """
    Establishes a connection to the database.
    """
    conn = pyodbc.connect(
        f"DRIVER={DB_CONFIG['DRIVER']};"
        f"SERVER={DB_CONFIG['SERVER']};"
        f"DATABASE={DB_CONFIG['DATABASE']};"
        f"UID={DB_CONFIG['UID']};"
        f"PWD={DB_CONFIG['PWD']};"
    )
    return conn

def initialize_db():
    """
    Initializes the database by creating necessary tables if they don't exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Table for Categories
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name='Categories')
        CREATE TABLE Categories (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL
        )""")

        # Table for Files with external links
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name='CategoryFiles')
        CREATE TABLE CategoryFiles (
            id INT IDENTITY(1,1) PRIMARY KEY,
            category_id INT NOT NULL,
            file_name VARCHAR(255),
            file_path VARCHAR(500),
            external_link VARCHAR(500), -- New column for storing links
            total_duration FLOAT, -- Total duration of the video in seconds
            FOREIGN KEY (category_id) REFERENCES Categories(id) ON DELETE CASCADE
        )""")

        # Table for User-Specific Video Progress
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name='UserVideoProgress')
        CREATE TABLE UserVideoProgress (
            id INT IDENTITY(1,1) PRIMARY KEY,
            user_id INT NOT NULL,
            file_id INT NOT NULL,
            watched_duration FLOAT DEFAULT 0, -- Duration watched by the user in seconds
            FOREIGN KEY (user_id) REFERENCES Employees(ID) ON DELETE CASCADE,
            FOREIGN KEY (file_id) REFERENCES CategoryFiles(id) ON DELETE CASCADE
        )""")

        # Table for Employee Category Access
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name='EmployeeCategoryAccess')
        CREATE TABLE EmployeeCategoryAccess (
            id INT IDENTITY(1,1) PRIMARY KEY,
            employee_id INT NOT NULL,
            category_id INT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES Employees(ID) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES Categories(id) ON DELETE CASCADE
        )""")

        conn.commit()
        print("All tables created successfully.")
    except Exception as e:
        print("Error creating tables:", e)
    finally:
        cursor.close()
        conn.close()

# Initialize the database
initialize_db()