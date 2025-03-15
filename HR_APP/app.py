from fastapi import FastAPI, UploadFile, File, Form,HTTPException,Depends
from typing import List, Optional
import pyodbc
import shutil
import os
from fastapi.middleware.cors import CORSMiddleware
import ffmpeg
from datetime import datetime
import yt_dlp
from pydantic import BaseModel
# FastAPI instance
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change "*" to your frontend URL for security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Database Connection
DB_CONFIG = {
    "DRIVER": "{ODBC Driver 17 for SQL Server}",
    "SERVER": "40.121.205.186",
    "DATABASE": "HRVMS_test",
    "UID": "saclient",
    "PWD": "#Client!!#Server@890*"
}

def get_db_connection():
    conn = pyodbc.connect(
        f"DRIVER={DB_CONFIG['DRIVER']};"
        f"SERVER={DB_CONFIG['SERVER']};"
        f"DATABASE={DB_CONFIG['DATABASE']};"
        f"UID={DB_CONFIG['UID']};"
        f"PWD={DB_CONFIG['PWD']};"
    )
    return conn


# Create Table if not exists
def initialize_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
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
        FOREIGN KEY (category_id) REFERENCES Categories(id) ON DELETE CASCADE
    )""")

    conn.commit()
    conn.close()

# Initialize DB on startup
initialize_db()

# Upload directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# User Login Schema
class LoginRequest(BaseModel):
    LoginUser: str
    LoginPassword: str

@app.post("/login/")
async def login(request: LoginRequest):
    """
    API to authenticate user using LoginUser and LoginPassword.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query to check user credentials
    cursor.execute(
        "SELECT ID, FirstName, LastName FROM Employees WHERE LoginUser=? AND LoginPassword=?",
        (request.LoginUser, request.LoginPassword)
    )
    user = cursor.fetchone()
    
    conn.close()
    
    if user:
        return {
            "message": "Login successful",
            "user_id": user.ID,
            "name": f"{user.FirstName} {user.LastName}"
        }
    else:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    
    
# Function to get video duration of uploaded files
def get_video_duration(file_path):
    try:
        probe = ffmpeg.probe(file_path)
        duration = float(probe["format"]["duration"])
        return duration
    except Exception as e:
        print(f"Error fetching uploaded video duration: {e}")
        return None

def format_duration(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def get_external_video_duration(url):
    try:
        ydl_opts = {"quiet": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration", None)  # Duration in seconds
            return duration if duration is not None else None
    except Exception as e:
        print(f"Error fetching duration: {e}")
        return None



# API to add a category with video files or external links
@app.post("/admin/add_category/")
async def add_category(
    name: str = Form(...), 
    files: List[UploadFile] = File(None),
    external_link: Optional[str] = Form(None),
    link_name: Optional[str] = Form(None)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert category
    cursor.execute("INSERT INTO Categories (name) OUTPUT INSERTED.id VALUES (?)", (name,))
    category_id = cursor.fetchone()[0]

    # Process uploaded files
    if files:
        for file in files:
            file_location = f"{UPLOAD_DIR}/{category_id}_{file.filename}"
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            video_duration = get_video_duration(file_location)

            cursor.execute(
            "INSERT INTO CategoryFiles (category_id, external_link, link_name, total_duration) VALUES (?, ?, ?, ?)",
            (category_id, external_link, link_name, video_duration),  # video_duration is now in seconds
        )


    # Process external links
    if external_link:
        video_duration = get_external_video_duration(external_link)
        cursor.execute(
            "INSERT INTO CategoryFiles (category_id, external_link, link_name, total_duration) VALUES (?, ?, ?, ?)",
            (category_id, external_link, link_name, video_duration),
        )

    conn.commit()
    conn.close()
    return {"message": "Category added successfully", "category_id": category_id}




@app.get("/user/{employee_id}/categories/")
async def get_user_categories(employee_id: int):
    """
    Fetch all categories accessible to the given employee.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.name 
        FROM Categories c
        JOIN EmployeeCategoryAccess eca ON c.id = eca.category_id
        WHERE eca.employee_id = ?
    """, (employee_id,))

    categories = [{"id": row.id, "name": row.name} for row in cursor.fetchall()]

    conn.close()
    return {"categories": categories}



# API to fetch all video files and links in a category
def format_duration(seconds):
    if seconds is None:
        return "00:00:00"  # Default value if duration is missing
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


@app.get("/user/{employee_id}/category/{category_id}/files/")
async def get_category_files(employee_id: int, category_id: int):
    """
    Fetch all files in a category only if the user has access.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the employee has access
    cursor.execute("SELECT * FROM EmployeeCategoryAccess WHERE employee_id=? AND category_id=?", (employee_id, category_id))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")

    # Fetch category files
    cursor.execute("SELECT id, external_link, link_name, total_duration, watched_duration FROM CategoryFiles WHERE category_id=?", (category_id,))
    
    files = []
    for row in cursor.fetchall():
        files.append({
            "file_id": row.id,
            "external_link": row.external_link,
            "link_name": row.link_name,
            "total_duration": format_duration(row.total_duration) if row.total_duration is not None else "00:00:00",
            "watched_duration": row.watched_duration,
        })

    conn.close()
    return {"category_id": category_id, "videos": files}


@app.get("/admin/employees/")
async def get_all_users():
    """
    Fetch all users from the Employees table.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT ID, FirstName + ' ' + LastName AS FullName, LoginUser,LoginPassword FROM Employees")
    users = [{"id": row.ID, "name": row.FullName, "username": row.LoginUser,"userpassword": row.LoginPassword} for row in cursor.fetchall()]
    conn.close()
    return {"users": users}


@app.post("/admin/grant_access/")
async def grant_category_access(
    user_id: int = Form(...),
    category_id: int = Form(...)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if access already exists
    cursor.execute(
        "SELECT * FROM EmployeeCategoryAccess WHERE employee_id=? AND category_id=?",
        (user_id, category_id)
    )
    if cursor.fetchone():
        conn.close()
        return {"message": "Access already granted"}

    # Grant access
    cursor.execute(
        "INSERT INTO EmployeeCategoryAccess (employee_id, category_id) VALUES (?, ?)",
        (user_id, category_id)
    )

    conn.commit()
    conn.close()
    return {"message": "Access granted successfully"}


@app.get("/categories/")
async def get_all_categories():
    """
    Fetch all categories from the database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM Categories")
    categories = [{"id": row.id, "name": row.name} for row in cursor.fetchall()]

    conn.close()
    return {"categories": categories}



@app.get("/admin/user_progress/")
async def get_user_progress():
    """
    Fetch user-wise progress for all videos.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            e.ID AS user_id,
            e.FirstName + ' ' + e.LastName AS user_name,
            cf.id AS file_id,
            cf.file_name,
            cf.external_link,
            cf.total_duration,
            uvp.watched_duration
        FROM Employees e
        LEFT JOIN UserVideoProgress uvp ON e.ID = uvp.user_id
        LEFT JOIN CategoryFiles cf ON uvp.file_id = cf.id
        ORDER BY e.ID, cf.id
    """)

    user_progress = {}
    for row in cursor.fetchall():
        user_id = row.user_id
        if user_id not in user_progress:
            user_progress[user_id] = {
                "user_name": row.user_name,
                "videos": []
            }
        
        user_progress[user_id]["videos"].append({
            "file_id": row.file_id,
            "file_name": row.file_name,
            "external_link": row.external_link,
            "total_duration": row.total_duration,
            "watched_duration": row.watched_duration
        })

    conn.close()
    return {"user_progress": user_progress}
    
    
@app.get("/admin/user_progress/")
async def get_user_progress():
    """
    Fetch user-wise progress for all videos.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            e.ID AS user_id,
            e.FirstName + ' ' + e.LastName AS user_name,
            cf.id AS file_id,
            cf.file_name,
            cf.external_link,
            cf.total_duration,
            uvp.watched_duration
        FROM Employees e
        LEFT JOIN UserVideoProgress uvp ON e.ID = uvp.user_id
        LEFT JOIN CategoryFiles cf ON uvp.file_id = cf.id
        ORDER BY e.ID, cf.id
    """)

    user_progress = {}
    for row in cursor.fetchall():
        user_id = row.user_id
        if user_id not in user_progress:
            user_progress[user_id] = {
                "user_name": row.user_name,
                "videos": []
            }
        
        user_progress[user_id]["videos"].append({
            "file_id": row.file_id,
            "file_name": row.file_name,
            "external_link": row.external_link,
            "total_duration": row.total_duration,
            "watched_duration": row.watched_duration
        })

    conn.close()
    return {"user_progress": user_progress}
    
@app.get("/user/{user_id}/progress/")
async def get_user_video_progress(user_id: int):
    """
    Fetch progress for all videos watched by a specific user.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            cf.id AS file_id,
            cf.file_name,
            cf.external_link,
            cf.total_duration,
            uvp.watched_duration
        FROM UserVideoProgress uvp
        JOIN CategoryFiles cf ON uvp.file_id = cf.id
        WHERE uvp.user_id = ?
    """, (user_id,))

    videos = []
    for row in cursor.fetchall():
        videos.append({
            "file_id": row.file_id,
            "file_name": row.file_name,
            "external_link": row.external_link,
            "total_duration": row.total_duration,
            "watched_duration": row.watched_duration
        })

    conn.close()
    return {"user_id": user_id, "videos": videos}


# API to update watched duration of a video
@app.post("/user/update_watched_duration/")
async def update_watched_duration(
    user_id: int = Form(...),
    file_id: int = Form(...),
    watched_duration: float = Form(...)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get total duration of the video
    cursor.execute("SELECT total_duration FROM CategoryFiles WHERE id = ?", (file_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return {"error": "File not found"}

    total_duration = result[0]

    # Ensure watched duration doesn't exceed total duration
    watched_duration = min(watched_duration, total_duration)

    # Check if the user already has progress for this file
    cursor.execute(
        "SELECT id FROM UserVideoProgress WHERE user_id = ? AND file_id = ?",
        (user_id, file_id)
    )
    progress = cursor.fetchone()

    if progress:
        # Update existing progress
        cursor.execute(
            "UPDATE UserVideoProgress SET watched_duration = ? WHERE id = ?",
            (watched_duration, progress[0]))  # Fixed: Added missing closing parenthesis
    else:
        # Insert new progress
        cursor.execute(
            "INSERT INTO UserVideoProgress (user_id, file_id, watched_duration) VALUES (?, ?, ?)",
            (user_id, file_id, watched_duration)
        )

    conn.commit()
    conn.close()
    return {"message": "Watched duration updated successfully"}