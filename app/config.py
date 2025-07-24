from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb+srv://emelygomez:BpGHOqzYhF9lNm9O@cluster0.mronmnn.mongodb.net/stroke_database"
    MONGODB_NAME: str = "stroke_database"  # Add this line
    PORT: int = 5000
    API_BASE_URL: str = "http://localhost:5000"  # Useful for image URLs

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()