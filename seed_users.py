import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import List, Dict
from app.config import settings
import logging
import bcrypt

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserSeeder:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URI)
        self.db = self.client.get_database("stroke_database")

    async def _hash_password(self, password: str) -> str:
        """Encripta la contraseña usando bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    async def _get_default_users(self) -> List[Dict]:
        """Define los usuarios por defecto con contraseñas seguras"""
        default_password = "P@ssw0rd123"  # Contraseña por defecto (debería ser cambiada)
        hashed_password = await self._hash_password(default_password)

        return [
            {
                "username": "admin",
                "full_name": "Administrador Sistema",
                "role": "admin",
                "password_hash": hashed_password,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True
            },
            {
                "username": "doctor",
                "full_name": "Dr. Juan Pérez",
                "role": "doctor",
                "password_hash": hashed_password,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True
            }
        ]

    async def _user_exists(self, username: str) -> bool:
        """Verifica si un usuario ya existe"""
        return await self.db.users.find_one({"username": username}) is not None

    async def seed_users(self):
        """Función principal para poblar la base de datos con usuarios iniciales"""
        try:
            users = await self._get_default_users()

            for user in users:
                if not await self._user_exists(user["username"]):
                    await self.db.users.insert_one(user)
                    logger.info(f"Usuario creado: {user['username']}")
                else:
                    logger.warning(f"Usuario {user['username']} ya existe, omitiendo")

            logger.info("Proceso de seeding completado exitosamente")
        except Exception as e:
            logger.error(f"Error durante el seeding: {str(e)}")
            raise
        finally:
            self.client.close()

async def main():
    seeder = UserSeeder()
    await seeder.seed_users()

if __name__ == "__main__":
    asyncio.run(main())