# core.py
import random
import string
import json
import os
from datetime import datetime
import bcrypt
from dotenv import load_dotenv
import streamlit as st 
import threading # Adicionado para Locks

# Carregar variáveis de ambiente
load_dotenv()

# Cache em memória global (da implementação anterior)
_GAMES_CACHE = {}
_TEACHERS_CACHE = {}

# Locks para proteger escrita nos arquivos JSON
_JSON_WRITE_LOCK_GAMES = threading.Lock()
_JSON_WRITE_LOCK_TEACHERS = threading.Lock()


# Função para criar o diretório de dados se não existir
def setup_data_directory():
    os.makedirs("data", exist_ok=True)

    teachers_file_path = "data/teachers.json"
    games_file_path = "data/games.json"

    # Protegendo a inicialização dos arquivos com locks também, por segurança
    with _JSON_WRITE_LOCK_TEACHERS:
        if not os.path.exists(teachers_file_path):
            demo_username = "professor"
            demo_plain_password = os.getenv("DEMO_PROFESSOR_PASSWORD")
            demo_name = os.getenv("DEMO_PROFESSOR_NAME", "Professor Demo")
            demo_email = os.getenv("DEMO_PROFESSOR_EMAIL", "professor@demo.com")

            if not demo_plain_password:
                print("------------------------------------------------------------------------------------")
                print("AVISO IMPORTANTE: 'DEMO_PROFESSOR_PASSWORD' não definida no .env.")
                print("(O arquivo 'data/teachers.json' será inicializado como um dicionário vazio.)")
                print("------------------------------------------------------------------------------------")
                with open(teachers_file_path, "w") as f:
                    json.dump({}, f)
            else:
                hashed_password = bcrypt.hashpw(demo_plain_password.encode('utf-8'), bcrypt.gensalt())
                teacher_data_demo = { # Renomeado para evitar conflito
                    "username": demo_username,
                    "password": hashed_password.decode('utf-8'),
                    "name": demo_name,
                    "email": demo_email,
                    "questions": [] 
                }
                with open(teachers_file_path, "w") as f:
                    json.dump({demo_username: teacher_data_demo}, f, indent=4)
                print(f"Arquivo '{teachers_file_path}' criado e usuário demo '{demo_username}' configurado.")
                if _TEACHERS_CACHE is not None:
                     _TEACHERS_CACHE[demo_username] = Teacher.from_dict(teacher_data_demo)

    with _JSON_WRITE_LOCK_GAMES:
        if not os.path.exists(games_file_path):
            with open(games_file_path, "w") as f:
                json.dump({}, f)
            print(f"Arquivo '{games_file_path}' criado.")

# Gerar código aleatório para jogos
def generate_game_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# Funções de utilidade para o cache (da implementação anterior)
def clear_game_from_cache(game_code):
    if game_code in _GAMES_CACHE:
        del _GAMES_CACHE[game_code]

def clear_teacher_from_cache(username):
    if username in _TEACHERS_CACHE:
        del _TEACHERS_CACHE[username]

def clear_all_teachers_from_cache():
    _TEACHERS_CACHE.clear()

def clear_all_games_from_cache(): 
    _GAMES_CACHE.clear()

# Classes para gerenciar os dados
class Teacher:
    def __init__(self, username, password, name, email):
        self.username = username
        self.password = password
        self.name = name
        self.email = email
        self.questions = []

    def to_dict(self):
        return {
            "username": self.username,
            "password": self.password,
            "name": self.name,
            "email": self.email,
            "questions": self.questions
        }

    @classmethod
    def from_dict(cls, data):
        teacher = cls(data["username"], data["password"], data["name"], data["email"])
        teacher.questions = data.get("questions", [])
        return teacher

    def add_question(self, question):
        self.questions.append(question)
        self.save()

    def save(self):
        # Adquire o lock antes de qualquer operação de I/O no arquivo de professores
        with _JSON_WRITE_LOCK_TEACHERS:
            try:
                with open("data/teachers.json", "r") as f:
                    teachers_data_on_disk = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                teachers_data_on_disk = {}
            
            teachers_data_on_disk[self.username] = self.to_dict()
            
            try:
                with open("data/teachers.json", "w") as f:
                    json.dump(teachers_data_on_disk, f, indent=4)
                # Atualizar cache APÓS salvar no disco e dentro do lock
                _TEACHERS_CACHE[self.username] = self
            except Exception as e:
                print(f"Erro ao salvar professor {self.username} no JSON: {e}")
                # Considerar se deve remover do cache em caso de falha no save
                # clear_teacher_from_cache(self.username) # Cuidado aqui, pois pode causar inconsistência

    @classmethod
    def get_by_username(cls, username):
        if username in _TEACHERS_CACHE:
            return _TEACHERS_CACHE[username]
        
        # A leitura não precisa estritamente do lock se as escritas são protegidas,
        # mas para consistência máxima em cenários de criação inicial de arquivo,
        # ou se o arquivo pudesse ser modificado externamente (não é o caso aqui),
        # um lock de leitura (ou o mesmo lock de escrita) poderia ser usado.
        # Por simplicidade, vamos omitir o lock na leitura aqui, pois as escritas são serializadas.
        try:
            with open("data/teachers.json", "r") as f:
                teachers_data_on_disk = json.load(f)
            if username in teachers_data_on_disk:
                teacher_obj = cls.from_dict(teachers_data_on_disk[username])
                _TEACHERS_CACHE[username] = teacher_obj 
                return teacher_obj
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            print("Erro ao decodificar data/teachers.json ao buscar professor.")
            return None
        return None

    @classmethod
    def create(cls, username, password, name, email):
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return cls(username, hashed_password, name, email)

class Game:
    def __init__(self, code, teacher_username, questions=None, players=None, status="waiting"):
        self.code = code
        self.teacher_username = teacher_username
        self.questions = questions or []
        self.players = players or {} 
        self.status = status 
        self.current_question = 0
        self.start_time = None
        self.question_start_time = None

    def to_dict(self):
        return {
            "code": self.code,
            "teacher_username": self.teacher_username,
            "questions": self.questions,
            "players": self.players,
            "status": self.status,
            "current_question": self.current_question,
            "start_time": self.start_time,
            "question_start_time": self.question_start_time
        }

    @classmethod
    def from_dict(cls, data):
        game = cls(
            data["code"],
            data["teacher_username"],
            data.get("questions", []),
            data.get("players", {}),
            data.get("status", "waiting")
        )
        game.current_question = data.get("current_question", 0)
        game.start_time = data.get("start_time")
        game.question_start_time = data.get("question_start_time")
        return game

    def add_player(self, nickname, icon):
        # A lógica de checagem do nickname não precisa do lock
        if nickname not in self.players:
            self.players[nickname] = {
                "icon": icon,
                "score": 0,
                "answers": []
            }
            self.save() 
            return True
        return False

    def start_game(self):
        self.status = "active"
        self.start_time = datetime.now().isoformat()
        self.question_start_time = datetime.now().isoformat()
        self.save()

    def next_question(self):
        if self.current_question < len(self.questions) - 1:
            self.current_question += 1
            self.question_start_time = datetime.now().isoformat()
            self.save()
            return True
        else:
            self.status = "finished"
            self.save()
            return False

    def record_answer(self, player_name, answer_index, time_taken):
        if player_name not in self.players or \
           self.current_question >= len(self.questions) or \
           self.status != "active":
            return False, 0

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
        
        self.players[player_name]["answers"].append({
            "question": self.current_question,
            "answer": answer_index,
            "correct": is_correct,
            "time": round(time_taken, 2),
            "points": points
        })
        self.players[player_name]["score"] += points
        self.save()
        return is_correct, points

    def get_ranking(self):
        ranking = [{"name": name, "icon": data["icon"], "score": data["score"]} for name, data in self.players.items()]
        return sorted(ranking, key=lambda x: x["score"], reverse=True)

    def save(self):
        # Adquire o lock antes de qualquer operação de I/O no arquivo de jogos
        with _JSON_WRITE_LOCK_GAMES:
            try:
                with open("data/games.json", "r") as f:
                    games_data_on_disk = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                games_data_on_disk = {}
            
            games_data_on_disk[self.code] = self.to_dict()
            
            try:
                with open("data/games.json", "w") as f:
                    json.dump(games_data_on_disk, f, indent=4)
                # Atualizar cache APÓS salvar no disco e dentro do lock
                _GAMES_CACHE[self.code] = self
            except Exception as e:
                print(f"Erro ao salvar jogo {self.code} no JSON: {e}")
                # clear_game_from_cache(self.code) # Cuidado com a consistência

    @classmethod
    def get_by_code(cls, code):
        if code in _GAMES_CACHE:
            return _GAMES_CACHE[code]
        
        # Omissão do lock na leitura por simplicidade, assumindo escritas serializadas.
        try:
            with open("data/games.json", "r") as f:
                games_data_on_disk = json.load(f)
            if code in games_data_on_disk:
                game_obj = cls.from_dict(games_data_on_disk[code])
                _GAMES_CACHE[code] = game_obj 
                return game_obj
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            print("Erro ao decodificar data/games.json ao buscar jogo por código.")
            return None
        return None
    
    @classmethod
    def get_by_teacher(cls, teacher_username):
        # Leitura do disco. Para consistência, se o jogo estiver no cache, usamos essa instância.
        # Esta função é menos crítica para performance que get_by_code.
        try:
            with open("data/games.json", "r") as f: # Leitura não precisa de lock se escritas são seguras
                games_data = json.load(f)
            
            teacher_games_from_disk = []
            for data in games_data.values():
                if data.get("teacher_username") == teacher_username:
                    if data["code"] in _GAMES_CACHE:
                        teacher_games_from_disk.append(_GAMES_CACHE[data["code"]])
                    else:
                        game_obj = cls.from_dict(data)
                        _GAMES_CACHE[data["code"]] = game_obj 
                        teacher_games_from_disk.append(game_obj)
            return teacher_games_from_disk
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            print("Erro ao decodificar data/games.json ao buscar jogos por professor.")
            return []

# SAMPLE_QUESTIONS e PLAYER_ICONS permanecem os mesmos.
SAMPLE_QUESTIONS = [
    {
        "question": "Qual é a capital do Brasil?",
        "options": ["Rio de Janeiro", "São Paulo", "Brasília", "Salvador"],
        "correct": 2
    },
    {
        "question": "Quanto é 7 x 8?",
        "options": ["54", "56", "64", "72"],
        "correct": 1
    },
    {
        "question": "Qual é o planeta mais próximo do Sol?",
        "options": ["Vênus", "Mercúrio", "Terra", "Marte"],
        "correct": 1
    },
    {
        "question": "Qual é o maior oceano do mundo?",
        "options": ["Atlântico", "Índico", "Pacífico", "Ártico"],
        "correct": 2
    },
    {
        "question": "Quem escreveu 'Dom Casmurro'?",
        "options": ["José de Alencar", "Machado de Assis", "Carlos Drummond de Andrade", "Clarice Lispector"],
        "correct": 1
    },
    {
        "question": "Qual é o elemento químico com símbolo 'O'?",
        "options": ["Ouro", "Oxigênio", "Ósmio", "Ogâneo"],
        "correct": 1
    },
    {
        "question": "Em que ano o Brasil foi descoberto?",
        "options": ["1492", "1500", "1530", "1549"],
        "correct": 1
    },
    {
        "question": "Qual é o maior mamífero terrestre?",
        "options": ["Elefante Africano", "Rinoceronte", "Girafa", "Hipopótamo"],
        "correct": 0
    },
    {
        "question": "Qual é a fórmula química da água?",
        "options": ["H2O", "CO2", "O2", "H2SO4"],
        "correct": 0
    },
    {
        "question": "Quem pintou a 'Mona Lisa'?",
        "options": ["Vincent van Gogh", "Pablo Picasso", "Leonardo da Vinci", "Michelangelo"],
        "correct": 2
    }
]
PLAYER_ICONS = ["😀", "😎", "🤖", "👻", "🦄", "🐱", "🐶", "🦊", "🐼", "🐯", "🦁", "🐸", "🐙", "🦋", "🦜", "💩", "🤓", "🧐", "😡", "🤩", "🤯", "🥶", "👹", "🤡", "👽", "💀", "👦🏼", "👩🏼", "🎃", "👦🏿", "👩🏿", "🐧", "🐺", "🐰", "🐭"]