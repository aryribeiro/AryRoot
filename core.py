# core.py
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
from typing import Dict, Optional, Any
import logging
from functools import wraps
import uuid

# Carregar variáveis de ambiente
load_dotenv()

DATABASE_PATH = "data/database.db"

# Cache em memória com TTL
class MemoryCache:
    def __init__(self, default_ttl: int = 30):
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

# Cache global - Correção: usar default_ttl em vez de ttl
game_cache = MemoryCache(default_ttl=5)  # Cache de jogos por 5 segundos
teacher_cache = MemoryCache(default_ttl=60)  # Cache de professores por 60 segundos

# Connection pool simplificado
class ConnectionPool:
    def __init__(self, max_connections: int = 20):
        self._connections = []
        self._lock = threading.RLock()
        self.max_connections = max_connections
    
    def get_connection(self):
        with self._lock:
            if self._connections:
                return self._connections.pop()
            return self._create_connection()
    
    def return_connection(self, conn):
        with self._lock:
            if len(self._connections) < self.max_connections:
                self._connections.append(conn)
            else:
                conn.close()
    
    def _create_connection(self):
        conn = sqlite3.connect(DATABASE_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=memory")
        return conn

# Pool de conexões global
db_pool = ConnectionPool()

# Retry decorator com backoff exponencial
def retry_db_operation(max_retries: int = 3, base_delay: float = 0.1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        # Backoff exponencial com jitter
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                        time.sleep(delay)
                    continue
                except Exception as e:
                    # Outros erros não devem ser retentados
                    raise e
            raise last_exception
        return wrapper
    return decorator

# Context manager para conexões do pool
class PooledConnection:
    def __init__(self):
        self.conn = None
    
    def __enter__(self):
        self.conn = db_pool.get_connection()
        return self.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None:
                try:
                    self.conn.commit()
                except Exception:
                    self.conn.rollback()
            else:
                self.conn.rollback()
            db_pool.return_connection(self.conn)

@retry_db_operation()
def get_db_connection():
    return PooledConnection()

def setup_data_directory():
    os.makedirs("data", exist_ok=True)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Criar tabela de professores com índices
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
        
        # Criar índices para performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_status ON games(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_teacher ON games(teacher_username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_updated ON games(updated_at)')

        # Verificar se o professor demo precisa ser inserido
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
                    print(f"Usuário demo '{demo_username}' configurado no banco de dados SQLite.")
                except sqlite3.Error as e:
                    print(f"Erro ao inserir professor demo no SQLite: {e}")

def generate_game_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

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
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                data = self.to_dict_for_db()
                cursor.execute('''
                INSERT OR REPLACE INTO teachers (username, password, name, email, questions, updated_at)
                VALUES (:username, :password, :name, :email, :questions, :updated_at)
                ''', data)
            
            # Atualizar cache
            teacher_cache.set(f"teacher:{self.username}", self)
        except Exception as e:
            print(f"Erro ao salvar professor {self.username}: {e}")
            raise

    @classmethod
    @retry_db_operation()
    def get_by_username(cls, username):
        # Verificar cache primeiro
        cached = teacher_cache.get(f"teacher:{username}")
        if cached:
            return cached
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM teachers WHERE username = ?", (username,))
                row = cursor.fetchone()
                teacher = cls.from_db_row(row)
                
                # Adicionar ao cache se encontrado
                if teacher:
                    teacher_cache.set(f"teacher:{username}", teacher)
                
                return teacher
        except Exception as e:
            print(f"Erro ao buscar professor {username}: {e}")
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
            print(f"Erro ao buscar professores: {e}")
            return []
    
    @classmethod
    @retry_db_operation()
    def delete_by_username(cls, username):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM teachers WHERE username = ?", (username,))
                success = cursor.rowcount > 0
                
            # Remover do cache
            teacher_cache.delete(f"teacher:{username}")
            return success
        except Exception as e:
            print(f"Erro ao deletar professor {username}: {e}")
            return False

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
        with self._lock:
            if nickname not in self.players:
                self.players[nickname] = {
                    "icon": icon,
                    "score": 0,
                    "answers": [],
                    "joined_at": datetime.now().isoformat()
                }
                self._force_save()
                return True
            return False

    def start_game(self):
        with self._lock:
            self.status = "active"
            self.start_time = datetime.now().isoformat()
            self.question_start_time = datetime.now().isoformat()
            self._force_save()

    def next_question(self):
        with self._lock:
            if self.current_question < len(self.questions) - 1:
                self.current_question += 1
                self.question_start_time = datetime.now().isoformat()
                self._force_save()
                return True
            else:
                self.status = "finished"
                self._force_save()
                return False

    def record_answer(self, player_name, answer_index, time_taken):
        with self._lock:
            if (player_name not in self.players or 
                self.current_question >= len(self.questions) or 
                self.status != "active"):
                return False, 0

            # Verificar se já respondeu esta pergunta
            player_data = self.players[player_name]
            if not isinstance(player_data, dict):
                return False, 0
                
            answers = player_data.get("answers", [])
            if any(ans.get("question") == self.current_question for ans in answers):
                return False, 0  # Já respondeu

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
            
            # Salvar periodicamente ou em mudanças importantes
            self._conditional_save()
            return is_correct, points

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
        """Salva apenas se passou tempo suficiente desde a última salvagem"""
        now = datetime.now()
        if (now - self._last_save).total_seconds() > 2:  # Salvar a cada 2 segundos
            self._force_save()

    def _force_save(self):
        """Força salvamento imediato"""
        try:
            self.save()
            self._last_save = datetime.now()
        except Exception as e:
            print(f"Erro ao salvar jogo {self.code}: {e}")

    @retry_db_operation()
    def save(self):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                data = self.to_dict_for_db()
                cursor.execute('''
                INSERT OR REPLACE INTO games 
                (code, teacher_username, questions, players, status, current_question, start_time, question_start_time, updated_at)
                VALUES (:code, :teacher_username, :questions, :players, :status, :current_question, :start_time, :question_start_time, :updated_at)
                ''', data)
            
            # Atualizar cache
            game_cache.set(f"game:{self.code}", self)
        except Exception as e:
            print(f"Erro ao salvar jogo {self.code}: {e}")
            raise

    @classmethod
    @retry_db_operation()
    def get_by_code(cls, code):
        # Verificar cache primeiro
        cached = game_cache.get(f"game:{code}")
        if cached:
            return cached
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM games WHERE code = ?", (code,))
                row = cursor.fetchone()
                game = cls.from_db_row(row)
                
                # Adicionar ao cache se encontrado
                if game:
                    game_cache.set(f"game:{code}", game)
                
                return game
        except Exception as e:
            print(f"Erro ao buscar jogo {code}: {e}")
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
                
                # Adicionar ao cache
                for game in games:
                    if game:
                        game_cache.set(f"game:{game.code}", game)
                
                return games
        except Exception as e:
            print(f"Erro ao buscar jogos do professor {teacher_username}: {e}")
            return []

# SAMPLE_QUESTIONS e PLAYER_ICONS permanecem os mesmos
SAMPLE_QUESTIONS = [
  {
    "question": "A camada de banco de dados de um aplicativo Web está sendo executada em um servidor Windows local. O banco de dados é um banco de dados Microsoft SQL Server. O proprietário do aplicativo gostaria de migrar o banco de dados para uma instância do Amazon RDS. Como a migração pode ser executada com o mínimo de esforço administrativo e tempo de inatividade?",
    "options": [
      "Usar o AWS Server Migration Service (SMS) para migrar o servidor para o Amazon EC2. Usar o AWS Database Migration Service (DMS) para migrar o banco de dados para o RDS",
      "Usar o AWS Database Migration Service (DMS) para migrar diretamente o banco de dados para o RDS.",
      "Usar a Schema Conversion Tool (SCT) para habilitar a conversão do Microsoft SQL Server para o Amazon RDS",
      "Usar o AWS DataSync para migrar os dados do banco de dados para o Amazon S3. Usar o AWS Database Migration Service (DMS) para migrar o banco de dados para o RDS"
    ],
    "correct": 1
  },  
  {
    "question": "Existem dois aplicativos em uma empresa: um aplicativo remetente que envia mensagens contendo cargas úteis e um aplicativo de processamento que recebe mensagens contendo cargas úteis. A empresa deseja implementar um serviço da AWS para lidar com mensagens entre esses dois aplicativos diferentes. O aplicativo remetente envia em média 1.000 mensagens por hora e as mensagens dependendo do tipo às vezes levam até 2 dias para serem processadas. Se as mensagens falharem no processamento, elas devem ser retidas para que não afetem o processamento de nenhuma mensagem restante. Qual solução atende a esses requisitos e é a MAIS eficiente operacionalmente?",
    "options": [
      "Configure um banco de dados Redis no Amazon EC2. Configure a instância a ser usada por ambos os aplicativos. As mensagens devem ser armazenadas, processadas e excluídas, respectivamente",
      "Inscrever o aplicativo de processamento em um tópico do Amazon Simple Notification Service (Amazon SNS) para receber notificações. Gravar no tópico do SNS usando o aplicativo do remetente",
      "Receber as mensagens do aplicativo remetente usando um stream de dados do Amazon Kinesis. Utilizar a Kinesis Client Library (KCL) para integrar o aplicativo de processamento",
      "Fornecer uma fila do Amazon Simple Queue Service (Amazon SQS) para os aplicativos do remetente e do processador. Configurar uma fila de mensagens mortas para coletar mensagens com falha"
    ],
    "correct": 3
  }
]

PLAYER_ICONS = ["😀", "😎", "🤖", "👻", "🦄", "🐱", "🐶", "🦊", "🐼", "🐯", "🦁", "🐸", "🐙", "🦋", "🦜", "💩", "🤓", "🧐", "😡", "🤩", "🤯", "🥶", "👹", "🤡", "👽", "💀", "👦🏼", "👩🏼", "🎃", "👦🏿", "👩🏿", "🐧", "🐺", "🐰", "🐭"]