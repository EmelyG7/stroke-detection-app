from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        if not self.client:
            self.client = AsyncIOMotorClient(settings.MONGODB_URI)
            self.db = self.client.get_database(settings.MONGODB_NAME)  # Updated this line
        return self.db

    async def close(self):
        if self.client:
            await self.client.close()
            self.client = None
            self.db = None

db = Database()