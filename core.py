# core.py - FIXED VERSION
import random
import string
import json
import os
from datetime import datetime, timedelta
import bcrypt
from dotenv import load_dotenv
import sqlite3
import streamlit as st
import time
import threading
from typing import Dict, Optional, Any, List, Tuple
import logging
from functools import wraps
import uuid
from enum import Enum
from contextlib import contextmanager

# Configurar logging estruturado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_PATH = "data/database.db"

# ==================== CIRCUIT BREAKER ====================
class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """Circuit Breaker com 3 estados para prevenir cascading failures"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        self._lock = threading.RLock()
    
    def call(self, func, *args, **kwargs):
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker: OPEN -> HALF_OPEN")
                else:
                    raise Exception("Circuit breaker is OPEN")
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise e
    
    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        return (datetime.now() - self.last_failure_time).total_seconds() >= self.recovery_timeout
    
    def _on_success(self):
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("Circuit breaker: HALF_OPEN -> CLOSED")
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker: -> OPEN (failures: {self.failure_count})")

# Circuit breaker global para operações de DB
db_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

# ==================== MEMORY CACHE ====================
class MemoryCache:
    """Cache em memória com TTL - FIXED: default_ttl parameter"""
    
    def __init__(self, default_ttl: int = 30):  # FIX: era ttl=30
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if datetime.now() < entry['expires']:
                    return entry['data']
                else:
                    del self._cache[key]
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl or self.default_ttl
        expires = datetime.now() + timedelta(seconds=ttl)
        with self._lock:
            self._cache[key] = {'data': value, 'expires': expires}
    
    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

# Caches globais com TTL corrigido
game_cache = MemoryCache(default_ttl=5)
teacher_cache = MemoryCache(default_ttl=60)

# ==================== DEDUPLICATION CACHE ====================
class DeduplicationCache:
    """Cache para prevenir operações duplicadas (idempotência)"""
    
    def __init__(self, ttl: int = 300):
        self._cache: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self.ttl = ttl
    
    def exists(self, operation_id: str) -> bool:
        with self._lock:
            return operation_id in self._cache
    
    def get(self, operation_id: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(operation_id)
            if entry and datetime.now() < entry['expires']:
                return entry['data']
            elif entry:
                del self._cache[operation_id]
            return None
    
    def set(self, operation_id: str, result: Any) -> None:
        with self._lock:
            expires = datetime.now() + timedelta(seconds=self.ttl)
            self._cache[operation_id] = {'data': result, 'expires': expires}

dedup_cache = DeduplicationCache(ttl=300)

# ==================== CONNECTION POOL ====================
class ConnectionPool:
    """Connection pool com cleanup garantido - FIXED: leak prevention"""
    
    def __init__(self, max_connections: int = 20):
        self._connections = []
        self._lock = threading.RLock()
        self.max_connections = max_connections
        self._active_count = 0
    
    def get_connection(self):
        with self._lock:
            if self._connections:
                self._active_count += 1
                return self._connections.pop()
            return self._create_connection()
    
    def return_connection(self, conn):
        with self._lock:
            try:
                self._active_count -= 1
                if len(self._connections) < self.max_connections and conn:
                    # Verificar se connection ainda é válida
                    conn.execute("SELECT 1")
                    self._connections.append(conn)
                elif conn:
                    conn.close()
            except Exception as e:
                logger.warning(f"Connection cleanup error: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def _create_connection(self):
        try:
            conn = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=memory")
            self._active_count += 1
            return conn
        except Exception as e:
            logger.error(f"Failed to create DB connection: {e}")
            raise

db_pool = ConnectionPool()

# ==================== DISTRIBUTED LOCK ====================
class DistributedLock:
    """Lock distribuído usando SQLite para concurrency control"""
    
    def __init__(self, key: str, timeout: int = 10):
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.lock_id = str(uuid.uuid4())
        self._acquired = False
    
    def acquire(self) -> bool:
        """Adquire lock com timeout"""
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    # Tentar criar lock row
                    cursor.execute('''
                        INSERT OR IGNORE INTO locks (key, lock_id, expires_at)
                        VALUES (?, ?, datetime('now', '+10 seconds'))
                    ''', (self.key, self.lock_id))
                    
                    if cursor.rowcount > 0:
                        self._acquired = True
                        return True
                    
                    # Limpar locks expirados
                    cursor.execute("DELETE FROM locks WHERE expires_at < datetime('now')")
                    
            except Exception as e:
                logger.warning(f"Lock acquire error: {e}")
            
            time.sleep(0.05)  # 50ms backoff
        
        return False
    
    def release(self):
        """Release lock apenas se owner"""
        if not self._acquired:
            return
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM locks WHERE key = ? AND lock_id = ?", 
                             (self.key, self.lock_id))
                self._acquired = False
        except Exception as e:
            logger.error(f"Lock release error: {e}")
    
    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Failed to acquire lock: {self.key}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

# ==================== GET DB CONNECTION ====================
@contextmanager
def get_db_connection():
    """Context manager para conexões do pool - FIXED: retorna conexão real"""
    conn = None
    try:
        conn = db_pool.get_connection()
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception as rollback_error:
                logger.error(f"Rollback error: {rollback_error}")
        raise e
    finally:
        if conn:
            db_pool.return_connection(conn)

# ==================== RETRY WITH JITTER ====================
def exponential_backoff_with_jitter(attempt: int, base_delay: float = 0.1, max_delay: float = 10.0) -> float:
    """Calcula delay com exponential backoff + 30% jitter"""
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * 0.3)
    return delay + jitter

def retry_db_operation(max_retries: int = 3, base_delay: float = 0.1):
    """Retry decorator com circuit breaker + exponential backoff + jitter - FIXED"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    # Usar circuit breaker
                    return db_circuit_breaker.call(func, *args, **kwargs)
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                    last_exception = e
                    logger.warning(f"DB operation failed (attempt {attempt+1}/{max_retries}): {e}")
                    
                    if attempt < max_retries - 1:
                        delay = exponential_backoff_with_jitter(attempt, base_delay)
                        time.sleep(delay)
                    continue
                except Exception as e:
                    # Outros erros não devem ser retentados
                    logger.error(f"Non-retryable error: {e}")
                    raise e
            
            logger.error(f"DB operation failed after {max_retries} retries")
            raise last_exception
        return wrapper
    return decorator

# ==================== DATABASE SETUP ====================
def setup_data_directory():
    """Setup com schema versioning - FIXED: uso correto do context manager"""
    os.makedirs("data", exist_ok=True)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Criar tabela de locks para distributed locking
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS locks (
            key TEXT PRIMARY KEY,
            lock_id TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_locks_expires ON locks(expires_at)')

        # Criar tabela de professores
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            questions TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Criar tabela de jogos com índices otimizados
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            code TEXT PRIMARY KEY,
            teacher_username TEXT NOT NULL,
            questions TEXT DEFAULT '[]',
            players TEXT DEFAULT '{}',
            status TEXT DEFAULT 'waiting',
            current_question INTEGER DEFAULT 0,
            start_time TEXT,
            question_start_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_username) REFERENCES teachers (username)
        )
        ''')
        
        # Índices compostos para performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_status ON games(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_teacher ON games(teacher_username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_status_teacher ON games(status, teacher_username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_updated ON games(updated_at)')

        # Inserir professor demo
        cursor.execute("SELECT COUNT(*) FROM teachers WHERE username = ?", ("professor",))
        if cursor.fetchone()[0] == 0:
            demo_username = "professor"
            demo_plain_password = os.getenv("DEMO_PROFESSOR_PASSWORD")
            demo_name = os.getenv("DEMO_PROFESSOR_NAME", "Professor Demo")
            demo_email = os.getenv("DEMO_PROFESSOR_EMAIL", "professor@demo.com")

            if demo_plain_password:
                hashed_password = bcrypt.hashpw(demo_plain_password.encode('utf-8'), bcrypt.gensalt())
                teacher_data_demo = {
                    "username": demo_username,
                    "password": hashed_password.decode('utf-8'),
                    "name": demo_name,
                    "email": demo_email,
                    "questions": json.dumps(SAMPLE_QUESTIONS)
                }
                try:
                    cursor.execute('''
                    INSERT INTO teachers (username, password, name, email, questions)
                    VALUES (:username, :password, :name, :email, :questions)
                    ''', teacher_data_demo)
                    logger.info(f"Demo user '{demo_username}' created")
                except sqlite3.Error as e:
                    logger.error(f"Failed to create demo user: {e}")

def generate_game_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ==================== TEACHER MODEL ====================
class Teacher:
    def __init__(self, username, password, name, email, questions_json_str="[]"):
        self.username = username
        self.password = password
        self.name = name
        self.email = email
        try:
            self.questions = json.loads(questions_json_str) if questions_json_str else []
        except json.JSONDecodeError:
            self.questions = []

    def to_dict_for_db(self):
        return {
            "username": self.username,
            "password": self.password,
            "name": self.name,
            "email": self.email,
            "questions": json.dumps(self.questions),
            "updated_at": datetime.now().isoformat()
        }

    @classmethod
    def from_db_row(cls, row):
        if not row:
            return None
        return cls(row["username"], row["password"], row["name"], row["email"], row["questions"])

    def add_question(self, question):
        if not isinstance(self.questions, list):
             self.questions = []
        self.questions.append(question)
        self.save()

    @retry_db_operation()
    def save(self):
        """Save com write-through cache - FIXED: cache consistency"""
        operation_id = f"save_teacher:{self.username}:{uuid.uuid4()}"
        
        # Check deduplication
        if dedup_cache.exists(operation_id):
            logger.info(f"Duplicate save_teacher operation detected: {self.username}")
            return dedup_cache.get(operation_id)
        
        try:
            # Use distributed lock
            with DistributedLock(f"teacher:{self.username}", timeout=5):
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    data = self.to_dict_for_db()
                    cursor.execute('''
                    INSERT OR REPLACE INTO teachers (username, password, name, email, questions, updated_at)
                    VALUES (:username, :password, :name, :email, :questions, :updated_at)
                    ''', data)
                
                # Update cache on success
                teacher_cache.set(f"teacher:{self.username}", self)
                dedup_cache.set(operation_id, True)
                logger.info(f"Teacher saved: {self.username}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save teacher {self.username}: {e}")
            raise

    @classmethod
    @retry_db_operation()
    def get_by_username(cls, username):
        # Check cache first
        cached = teacher_cache.get(f"teacher:{username}")
        if cached:
            return cached
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM teachers WHERE username = ?", (username,))
                row = cursor.fetchone()
                teacher = cls.from_db_row(row)
                
                if teacher:
                    teacher_cache.set(f"teacher:{username}", teacher)
                
                return teacher
        except Exception as e:
            logger.error(f"Failed to get teacher {username}: {e}")
            return None

    @classmethod
    def create(cls, username, password, name, email):
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return cls(username, hashed_password, name, email)

    @classmethod
    @retry_db_operation()
    def get_all_teachers_except_admin(cls):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM teachers WHERE username != 'professor' ORDER BY created_at DESC")
                rows = cursor.fetchall()
                return [cls.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get teachers: {e}")
            return []
    
    @classmethod
    @retry_db_operation()
    def delete_by_username(cls, username):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM teachers WHERE username = ?", (username,))
                success = cursor.rowcount > 0
                
            teacher_cache.delete(f"teacher:{username}")
            logger.info(f"Teacher deleted: {username}")
            return success
        except Exception as e:
            logger.error(f"Failed to delete teacher {username}: {e}")
            return False

# ==================== GAME MODEL ====================
class Game:
    def __init__(self, code, teacher_username, questions_json_str="[]", players_json_str="{}", 
                 status="waiting", current_question=0, start_time=None, question_start_time=None):
        self.code = code
        self.teacher_username = teacher_username
        self._lock = threading.RLock()
        
        try:
            self.questions = json.loads(questions_json_str) if questions_json_str else []
        except json.JSONDecodeError:
            self.questions = []
            
        try:
            self.players = json.loads(players_json_str) if players_json_str else {}
        except json.JSONDecodeError:
            self.players = {}
            
        self.status = status 
        self.current_question = current_question
        self.start_time = start_time
        self.question_start_time = question_start_time
        self._last_save = datetime.now()

    def to_dict_for_db(self):
        return {
            "code": self.code,
            "teacher_username": self.teacher_username,
            "questions": json.dumps(self.questions),
            "players": json.dumps(self.players),
            "status": self.status,
            "current_question": self.current_question,
            "start_time": self.start_time,
            "question_start_time": self.question_start_time,
            "updated_at": datetime.now().isoformat()
        }

    @classmethod
    def from_db_row(cls, row):
        if not row:
            return None
        return cls(
            row["code"], row["teacher_username"], row["questions"], row["players"],
            row["status"], row["current_question"], row["start_time"], row["question_start_time"]
        )

    def add_player(self, nickname, icon):
        """Add player com idempotência - FIXED: race condition"""
        operation_id = f"add_player:{self.code}:{nickname}"
        
        # Check deduplication
        if dedup_cache.exists(operation_id):
            logger.info(f"Duplicate add_player detected: {nickname}")
            return dedup_cache.get(operation_id)
        
        with DistributedLock(f"game:{self.code}", timeout=5):
            # Reload from DB to get fresh state
            fresh_game = Game.get_by_code(self.code)
            if fresh_game:
                self.players = fresh_game.players
            
            if nickname not in self.players:
                self.players[nickname] = {
                    "icon": icon,
                    "score": 0,
                    "answers": [],
                    "joined_at": datetime.now().isoformat()
                }
                self._force_save()
                dedup_cache.set(operation_id, True)
                logger.info(f"Player added: {nickname} to game {self.code}")
                return True
            
            dedup_cache.set(operation_id, False)
            return False

    def start_game(self):
        with DistributedLock(f"game:{self.code}", timeout=5):
            self.status = "active"
            self.start_time = datetime.now().isoformat()
            self.question_start_time = datetime.now().isoformat()
            self._force_save()
            logger.info(f"Game started: {self.code}")

    def next_question(self):
        with DistributedLock(f"game:{self.code}", timeout=5):
            if self.current_question < len(self.questions) - 1:
                self.current_question += 1
                self.question_start_time = datetime.now().isoformat()
                self._force_save()
                logger.info(f"Next question: {self.code} Q{self.current_question}")
                return True
            else:
                self.status = "finished"
                self._force_save()
                logger.info(f"Game finished: {self.code}")
                return False

    def record_answer(self, player_name, answer_index, time_taken):
        """Record answer com lock atomico - FIXED: race condition"""
        operation_id = f"answer:{self.code}:{player_name}:{self.current_question}"
        
        # Check deduplication (previne double-click)
        if dedup_cache.exists(operation_id):
            result = dedup_cache.get(operation_id)
            logger.info(f"Duplicate answer detected: {player_name}")
            return result if result else (False, 0)
        
        with DistributedLock(f"game:{self.code}:player:{player_name}", timeout=5):
            # Reload fresh state
            fresh_game = Game.get_by_code(self.code)
            if fresh_game:
                self.players = fresh_game.players
            
            if (player_name not in self.players or 
                self.current_question >= len(self.questions) or 
                self.status != "active"):
                result = (False, 0)
                dedup_cache.set(operation_id, result)
                return result

            # Verificar se já respondeu esta pergunta
            player_data = self.players[player_name]
            if not isinstance(player_data, dict):
                result = (False, 0)
                dedup_cache.set(operation_id, result)
                return result
                
            answers = player_data.get("answers", [])
            if any(ans.get("question") == self.current_question for ans in answers):
                result = (False, 0)
                dedup_cache.set(operation_id, result)
                return result

            # Calcular pontos
            correct_answer_idx = self.questions[self.current_question]["correct"]
            is_correct = (answer_index == correct_answer_idx)
            
            max_points = 1000
            min_points_correct = 100 
            time_penalty_cap = 20.0 

            points = 0
            if is_correct:
                points_reduction = (max_points - min_points_correct) * (min(time_taken, time_penalty_cap) / time_penalty_cap)
                points = int(max_points - points_reduction)
                points = max(min_points_correct, points)
            
            # Garantir que 'answers' existe e é uma lista
            if "answers" not in self.players[player_name] or not isinstance(self.players[player_name]["answers"], list):
                self.players[player_name]["answers"] = []

            self.players[player_name]["answers"].append({
                "question": self.current_question,
                "answer": answer_index,
                "correct": is_correct,
                "time": round(time_taken, 2),
                "points": points,
                "timestamp": datetime.now().isoformat()
            })
            self.players[player_name]["score"] += points
            
            self._force_save()
            
            result = (is_correct, points)
            dedup_cache.set(operation_id, result)
            logger.info(f"Answer recorded: {player_name} Q{self.current_question} correct={is_correct} points={points}")
            return result

    def get_ranking(self):
        with self._lock:
            if not isinstance(self.players, dict):
                return []
                
            ranking = []
            for name, data in self.players.items():
                if isinstance(data, dict):
                    ranking.append({
                        "name": name, 
                        "icon": data.get("icon", "❓"), 
                        "score": data.get("score", 0)
                    })
            return sorted(ranking, key=lambda x: x["score"], reverse=True)

    def _conditional_save(self):
        """Salva apenas se passou tempo suficiente"""
        now = datetime.now()
        if (now - self._last_save).total_seconds() > 2:
            self._force_save()

    def _force_save(self):
        """Força salvamento imediato"""
        try:
            self.save()
            self._last_save = datetime.now()
        except Exception as e:
            logger.error(f"Failed to save game {self.code}: {e}")

    @retry_db_operation()
    def save(self):
        """Save com write-through cache"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                data = self.to_dict_for_db()
                cursor.execute('''
                INSERT OR REPLACE INTO games 
                (code, teacher_username, questions, players, status, current_question, start_time, question_start_time, updated_at)
                VALUES (:code, :teacher_username, :questions, :players, :status, :current_question, :start_time, :question_start_time, :updated_at)
                ''', data)
            
            # Update cache on success
            game_cache.set(f"game:{self.code}", self)
        except Exception as e:
            logger.error(f"Failed to save game {self.code}: {e}")
            raise

    @classmethod
    @retry_db_operation()
    def get_by_code(cls, code):
        # Check cache first
        cached = game_cache.get(f"game:{code}")
        if cached:
            return cached
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM games WHERE code = ?", (code,))
                row = cursor.fetchone()
                game = cls.from_db_row(row)
                
                if game:
                    game_cache.set(f"game:{code}", game)
                
                return game
        except Exception as e:
            logger.error(f"Failed to get game {code}: {e}")
            return None
    
    @classmethod
    @retry_db_operation()
    def get_by_teacher(cls, teacher_username):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM games WHERE teacher_username = ? ORDER BY created_at DESC", (teacher_username,))
                rows = cursor.fetchall()
                games = [cls.from_db_row(row) for row in rows]
                
                # Add to cache
                for game in games:
                    if game:
                        game_cache.set(f"game:{game.code}", game)
                
                return games
        except Exception as e:
            logger.error(f"Failed to get games for teacher {teacher_username}: {e}")
            return []
    
    @classmethod
    @retry_db_operation()
    def get_multiple_by_codes(cls, codes: List[str]) -> Dict[str, 'Game']:
        """Batch fetch para reduzir N+1 queries - NEW"""
        if not codes:
            return {}
        
        # Check cache first
        result = {}
        missing_codes = []
        
        for code in codes:
            cached = game_cache.get(f"game:{code}")
            if cached:
                result[code] = cached
            else:
                missing_codes.append(code)
        
        if not missing_codes:
            return result
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join('?' * len(missing_codes))
                query = f"SELECT * FROM games WHERE code IN ({placeholders})"
                cursor.execute(query, missing_codes)
                
                for row in cursor:
                    game = cls.from_db_row(row)
                    if game:
                        result[game.code] = game
                        game_cache.set(f"game:{game.code}", game)
                
                return result
        except Exception as e:
            logger.error(f"Failed to batch get games: {e}")
            return result

# Sample questions
SAMPLE_QUESTIONS = [
  {
    "question": "Uma empresa utiliza duas contas AWS: produção e desenvolvimento. A empresa armazena os dados em um bucket Amazon S3 que está na conta de produção. Os dados são criptografados com uma chave gerenciada pelo cliente do AWS Key Management Service (AWS KMS). A empresa planeja copiar os dados para outro bucket S3 que esteja na conta de desenvolvimento. Um desenvolvedor precisa usar uma chave KMS para criptografar os dados no bucket S3 que está na conta de desenvolvimento. A chave KMS na conta de desenvolvimento deve estar acessível a partir da conta de produção. Qual solução atenderá a esses requisitos?",
    "options": [
      "Replicar a chave padrão gerenciada de KMS pela AWS para Amazon S3 da conta de produção para a conta de desenvolvimento. Especifique a conta de produção na política de chaves.",
      "Crie uma nova chave KMS gerenciada pelo cliente na conta de desenvolvimento. Especifique a conta de produção na política de chaves.",
      "Replicar a chave KMS gerenciada pelo cliente da conta de produção para a conta de desenvolvimento. Especifique a conta de produção na política de chaves.",
      "Crie uma nova chave KMS gerenciada pela AWS para o Amazon S3 na conta de desenvolvimento. Especifique a conta de produção na política de chaves."
    ],
    "correct": 1
  },
  {
    "question": "Uma empresa gera certificados SSL a partir de um provedor terceirizado. A empresa importa os certificados para o AWS Certificate Manager (ACM) para uso em aplicações web públicas. Um desenvolvedor deve implementar uma solução para notificar a equipe de segurança da empresa 90 dias antes do vencimento de um certificado importado. A empresa já configurou uma fila Amazon Simple Queue Service (Amazon SQS). A empresa também configurou um tópico Amazon Simple Notification Service (Amazon SNS) que contém o endereço de e-mail da equipe de segurança como assinante. Qual solução fornecerá à equipe de segurança a notificação necessária sobre os certificados?",
    "options": [
      "Crie uma função AWS Lambda para buscar todos os certificados que expiram em até 90 dias. Programe a função Lambda para enviar o Nome de Recursos Amazon (ARN) de cada certificado identificado em uma mensagem para a fila SQS.",
      "Crie uma regra Amazon EventBridge que especifique o tipo de evento de Certificado ACM que se aproxima da expiração. Defina o tópico da SNS como alvo da regra do EventBridge.",
      "Crie um fluxo de trabalho AWS Step Functions que seja invocado pela notificação de expiração de cada certificado pelo AWS CloudTrail. Crie uma função AWS Lambda para enviar o Nome de Recursos Amazon (ARN) de cada certificado em uma mensagem para a fila SQS.",
      "Configure o AWS Config com a regra gerenciada acm-certificate-expiration-check para rodar a cada 24 horas. Crie uma regra Amazon EventBridge que inclua um padrão de evento que especifique o tipo de detalhe de Conformidade das Regras de Configuração e a regra configurada. Defina o tópico da SNS como alvo da regra do EventBridge."
    ],
    "correct": 3
  },
  {
    "question": "Um desenvolvedor está implantando uma nova função AWS Lambda Node.js que não está conectada a uma VPC. A função Lambda precisa se conectar e consultar um banco de dados Amazon Aurora que não seja acessível publicamente. O desenvolvedor espera picos imprevisíveis no tráfego de banco de dados. O que o desenvolvedor deve fazer para dar acesso à função Lambda ao banco de dados?",
    "options": [
      "Configure a função Lambda para usar um proxy RDS da Amazon.",
      "Configure um gateway NAT. Anexe o gateway NAT à função Lambda.",
      "Ativem o acesso público no banco de dados Aurora. Configure um grupo de segurança no banco de dados para permitir o acesso de saída à porta do motor do banco de dados.",
      "Ative o acesso ao VPC para a função Lambda. Anexe a função Lambda a um novo grupo de segurança que não tenha regras."
    ],
    "correct": 0
  },
  {
    "question": "Um desenvolvedor está criando um aplicativo de negociação de ações. O desenvolvedor precisa de uma solução para enviar mensagens de texto aos usuários do aplicativo para confirmação quando uma negociação foi concluída. A solução deve entregar mensagens na ordem em que o usuário realiza as negociações de ações. A solução não deve enviar mensagens duplicadas. Qual solução atenderá a esses requisitos?",
    "options": [
      "Configure o aplicativo para publicar mensagens em um fluxo de entrega do Amazon Data Firehose. Configure o fluxo de entrega para ter um destino do número de celular de cada usuário que é passado na mensagem de confirmação de comércio.",
      "Crie uma fila FIFO do Amazon Simple Queue Service (Amazon SQS). Use a chamada da API SendMessageln para enviar as mensagens de confirmação de negociação para a fila. Use a API SendMessageOut para enviar as mensagens aos usuários utilizando as informações fornecidas na mensagem de confirmação de negociação.",
      "Configure um tubo no Amazon EventBridge Pipes. Conecte a aplicação ao tubo como fonte. Configure o tubo para usar o número de celular de cada usuário como alvo. Configure o pipeline para enviar eventos recebidos aos usuários.",
      "Crie um tópico FIFO do Amazon Simple Notification Service (SNS). Configure o aplicativo para usar o AWS SDK para publicar notificações no tópico da SNS e enviar mensagens SMS aos usuários."
    ],
    "correct": 3
  },
  {
    "question": "Um desenvolvedor precisa automatizar implantações para uma carga de trabalho serverless e baseada em eventos. O desenvolvedor precisa criar modelos padronizados para definir a infraestrutura e testar a funcionalidade da carga de trabalho localmente antes da implantação. O desenvolvedor já utiliza um pipeline no AWS CodePipeline. O desenvolvedor precisa incorporar quaisquer outras mudanças de infraestrutura no pipeline existente.\n\nQual solução atenderá a esses requisitos?",
    "options": [
      "Crie um modelo de Modelo de Aplicação Serverless AWS (AWS SAM). Configure os estágios do pipeline no CodePipeline para executar os comandos necessários da CLI SAM-AWS para implantar a carga de trabalho serverless.",
      "Crie um modelo de fluxo de trabalho AWS Step Functions baseado na infraestrutura usando a linguagem Amazon States. Inicie a máquina de estados Step Functions a partir do pipeline existente.",
      "Crie um modelo AWS CloudFormation. Use o fluxo de trabalho existente do pipeline para construir um pipeline para as pilhas AWS CloudFormation.",
      "Crie um modelo de Modelo de Aplicação Serverless AWS (AWS SAM). Use um script automatizado para implantar a carga de trabalho serverless usando o comando deploy da CLI DA AWS SAM."
    ],
    "correct": 0
  },
  {
    "question": "Um desenvolvedor está criando uma função AWS Lambda que precisa de acesso de rede a recursos privados em uma VPC. Qual solução vai proporcionar a esse acesso o MÍNIMO overhead operacional?",
    "options": [
      "Anexe a função Lambda à VPC por meio de sub-redes privadas. Crie um grupo de segurança que permita o acesso da rede aos recursos privados. Associe o grupo de segurança à função Lambda.",
      "Configure a função Lambda para rotear tráfego por uma conexão VPN. Crie um grupo de segurança que permita o acesso da rede aos recursos privados. Associe o grupo de segurança à função Lambda.",
      "Configure uma conexão de endpoint VPC para a função Lambda. Configure o endpoint da VPC para rotear o tráfego por um gateway NAT.",
      "Configure um endpoint AWS PrivateLink para os recursos privados. Configure a função Lambda para referenciar o endpoint PrivateLink."
    ],
    "correct": 0
  },
  {
    "question": "Um desenvolvedor está implantando uma aplicação em um cluster Amazon Elastic Container Service (Amazon ECS) que utiliza AWS Fargate. O desenvolvedor está usando um container Docker com uma imagem Ubuntu. O desenvolvedor precisa implementar uma solução para armazenar dados de aplicação disponíveis de múltiplas tarefas ECS. Os dados da aplicação devem permanecer acessíveis após o encerramento do container. Qual solução atenderá a esses requisitos?",
    "options": [
      "Anexe um volume do Amazon FSx for Windows File Server à definição do contêiner.",
      "Especifique o parâmetro DockerVolumeConfiguration na definição da tarefa do ECS para anexar um volume Docker.",
      "Crie um sistema de arquivos Amazon Elastic File System (Amazon EFS). Especifique o atributo mountPoints e o atributo efsVolumeConfiguration na definição da tarefa ECS.",
      "Crie um volume da Amazon Elastic Block Store (Amazon EBS). Especifique a configuração do ponto de montagem na definição da tarefa ECS."
    ],
    "correct": 2
  },
  {
    "question": "Uma equipe implanta um template AWS CloudFormation para atualizar uma pilha que já incluía uma tabela Amazon DynamoDB. No entanto, antes da implantação da atualização, a equipe mudou o nome da tabela DynamoDB no template por engano. O atributo DeletionPolicy para todos os recursos tem o valor padrão. Qual será o resultado desse erro?",
    "options": [
      "O CloudFormation criará uma nova tabela e apagará a tabela existente.",
      "O CloudFormation criará uma nova tabela e manterá a tabela existente.",
      "O CloudFormation irá sobrescrever a tabela existente e renomeá-la.",
      "O CloudFormation manterá a tabela existente e não criará uma nova tabela."
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa tem um aplicativo que roda em instâncias Amazon EC2. A aplicação precisa usar flags de recursos dinâmicos que serão compartilhados com outros aplicativos. O aplicativo deve consultar um intervalo para novos valores de flag de funcionalidades. Os valores devem ser armazenados em cache quando forem recuperados. Qual solução atenderá a esses requisitos da forma MAIS eficiente operacionalmente?",
    "options": [
      "Armazene os valores das flags de característica no AWS Secrets Manager. Configure um nó Amazon ElastiCache para armazenar os valores em cache usando uma estratégia de carregamento preguiçosa na aplicação. Atualize o aplicativo para consultar os valores em um intervalo a partir do ElastiCache.",
      "Armazene os valores das flags de características em uma tabela do Amazon DynamoDB. Configure o DynamoDB Accelerator (DAX) para armazenar os valores em cache usando uma estratégia de carregamento preguiçosa na aplicação. Atualize o aplicativo para consultar os valores em um intervalo a partir do DynamoDB.",
      "Armazene os valores das flags de característica no AWS AppConfig. Configure o AWS AppConfig Agent nas instâncias EC2 para consultar os valores em um intervalo. Atualize o aplicativo para recuperar os valores do endpoint localhost do AppConfig Agent.",
      "Armazene os valores das flags de característica na AWS Systems Manager Parameter Store. Configure o aplicativo para sondar em um intervalo. Configure a aplicação para usar o AWS SDK para recuperar os valores do Parameter Store e armazená-los na memória."
    ],
    "correct": 2
  },
  {
    "question": "Um desenvolvedor possui um contêiner de aplicação, uma função AWS Lambda e uma fila Amazon Simple Queue Service (Amazon SQS). A função Lambda usa a fila SQS como fonte de eventos. A função Lambda faz uma chamada para uma API de aprendizado de máquina de terceiros quando a função é invocada. A resposta da API de terceiros pode levar até 60 segundos para retornar. O valor de tempo limite da função Lambda atualmente é de 65 segundos. O desenvolvedor percebeu que a função Lambda às vezes processa mensagens duplicadas da fila SQS. O que o desenvolvedor deve fazer para garantir que a função Lambda não processe mensagens duplicadas?",
    "options": [
      "Configure a função Lambda com uma quantidade maior de memória.",
      "Configure um aumento no valor de timeout da função Lambda.",
      "Configure o valor de atraso de entrega da fila SQS para ser maior do que o tempo máximo necessário para chamar a API de terceiros.",
      "Configure o valor de tempo limite da fila SQS para ser maior do que o tempo máximo necessário para chamar a API de terceiros."
    ],
    "correct": 3
  }
]

PLAYER_ICONS = ["😀", "😎", "🤖", "👻", "🦄", "🐱", "🐶", "🦊", "🐼", "🐯", "🦁", "🐸", "🐙", "🦋", "🦜", "💩", "🤔", "🧐", "😡", "🤩", "🤯", "🥶", "👹", "🤡", "👽", "💀", "👦🏼", "👩🏼", "🎃", "👦🏿", "👩🏿", "🧙", "🐺", "🐰", "🐭"]