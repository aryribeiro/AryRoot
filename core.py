# core.py
import random
import string
import json
import os
from datetime import datetime
import bcrypt
from dotenv import load_dotenv
import sqlite3
import streamlit as st

# Carregar variáveis de ambiente
load_dotenv()

DATABASE_PATH = "data/database.db"

# Função para obter conexão com o banco de dados
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # Permite acessar colunas por nome
    return conn

# Função para criar o diretório de dados e inicializar o banco de dados
def setup_data_directory():
    os.makedirs("data", exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # Criar tabela de professores
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teachers (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        questions TEXT DEFAULT '[]'
    )
    ''')

    # Criar tabela de jogos
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
        FOREIGN KEY (teacher_username) REFERENCES teachers (username)
    )
    ''')

    # Verificar se o professor demo precisa ser inserido
    cursor.execute("SELECT COUNT(*) FROM teachers WHERE username = ?", ("professor",))
    if cursor.fetchone()[0] == 0:
        demo_username = "professor"
        demo_plain_password = os.getenv("DEMO_PROFESSOR_PASSWORD")
        demo_name = os.getenv("DEMO_PROFESSOR_NAME", "Professor Demo")
        demo_email = os.getenv("DEMO_PROFESSOR_EMAIL", "professor@demo.com")

        if not demo_plain_password:
            print("------------------------------------------------------------------------------------")
            print("AVISO IMPORTANTE: 'DEMO_PROFESSOR_PASSWORD' não definida no .env.")
            print("O usuário demo 'professor' não será criado automaticamente com senha.")
            print("------------------------------------------------------------------------------------")
        else:
            hashed_password = bcrypt.hashpw(demo_plain_password.encode('utf-8'), bcrypt.gensalt())
            teacher_data_demo = {
                "username": demo_username,
                "password": hashed_password.decode('utf-8'),
                "name": demo_name,
                "email": demo_email,
                "questions": json.dumps(SAMPLE_QUESTIONS) # Professor demo começa com as questões de exemplo
            }
            try:
                cursor.execute('''
                INSERT INTO teachers (username, password, name, email, questions)
                VALUES (:username, :password, :name, :email, :questions)
                ''', teacher_data_demo)
                conn.commit()
                print(f"Usuário demo '{demo_username}' configurado no banco de dados SQLite.")
            except sqlite3.Error as e:
                print(f"Erro ao inserir professor demo no SQLite: {e}")
    
    conn.close()

# Gerar código aleatório para jogos
def generate_game_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

class Teacher:
    def __init__(self, username, password, name, email, questions_json_str="[]"):
        self.username = username
        self.password = password # Deve ser o hash
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
            "questions": json.dumps(self.questions)
        }

    @classmethod
    def from_db_row(cls, row):
        if not row:
            return None
        return cls(row["username"], row["password"], row["name"], row["email"], row["questions"])

    def add_question(self, question):
        if not isinstance(self.questions, list): # Garantir que é uma lista
             self.questions = []
        self.questions.append(question)
        self.save()

    def save(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            data = self.to_dict_for_db()
            cursor.execute('''
            INSERT OR REPLACE INTO teachers (username, password, name, email, questions)
            VALUES (:username, :password, :name, :email, :questions)
            ''', data)
            conn.commit()
        except sqlite3.Error as e:
            print(f"Erro ao salvar professor {self.username} no SQLite: {e}")
            st.error(f"Erro de banco de dados ao salvar professor: {e}") # Para feedback ao usuário
        finally:
            conn.close()

    @classmethod
    def get_by_username(cls, username):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM teachers WHERE username = ?", (username,))
            row = cursor.fetchone()
            return cls.from_db_row(row)
        except sqlite3.Error as e:
            print(f"Erro ao buscar professor {username} no SQLite: {e}")
            st.error(f"Erro de banco de dados ao buscar professor: {e}")
            return None
        finally:
            conn.close()

    @classmethod
    def create(cls, username, password, name, email):
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        # questions_json_str é omitido, o construtor usará o default '[]'
        return cls(username, hashed_password, name, email)

    @classmethod
    def get_all_teachers_except_admin(cls):
        conn = get_db_connection()
        cursor = conn.cursor()
        teachers_list = []
        try:
            cursor.execute("SELECT * FROM teachers WHERE username != 'professor'")
            rows = cursor.fetchall()
            for row in rows:
                teachers_list.append(cls.from_db_row(row))
            return teachers_list
        except sqlite3.Error as e:
            print(f"Erro ao buscar todos os professores (exceto admin) no SQLite: {e}")
            st.error(f"Erro de banco de dados ao listar professores: {e}")
            return []
        finally:
            conn.close()
    
    @classmethod
    def delete_by_username(cls, username):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM teachers WHERE username = ?", (username,))
            conn.commit()
            return cursor.rowcount > 0 # Retorna True se alguma linha foi deletada
        except sqlite3.Error as e:
            print(f"Erro ao deletar professor {username} do SQLite: {e}")
            st.error(f"Erro de banco de dados ao deletar professor: {e}")
            return False
        finally:
            conn.close()


class Game:
    def __init__(self, code, teacher_username, questions_json_str="[]", players_json_str="{}", status="waiting", current_question=0, start_time=None, question_start_time=None):
        self.code = code
        self.teacher_username = teacher_username
        
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

    def to_dict_for_db(self):
        return {
            "code": self.code,
            "teacher_username": self.teacher_username,
            "questions": json.dumps(self.questions),
            "players": json.dumps(self.players),
            "status": self.status,
            "current_question": self.current_question,
            "start_time": self.start_time,
            "question_start_time": self.question_start_time
        }

    @classmethod
    def from_db_row(cls, row):
        if not row:
            return None
        return cls(
            row["code"],
            row["teacher_username"],
            row["questions"], # Passando como string JSON
            row["players"],   # Passando como string JSON
            row["status"],
            row["current_question"],
            row["start_time"],
            row["question_start_time"]
        )

    def add_player(self, nickname, icon):
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
        
        # Garante que 'answers' existe e é uma lista
        if "answers" not in self.players[player_name] or not isinstance(self.players[player_name]["answers"], list):
            self.players[player_name]["answers"] = []

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
        # Garante que self.players é um dicionário
        if not isinstance(self.players, dict):
            return []
            
        ranking = [{"name": name, "icon": data.get("icon", "❓"), "score": data.get("score", 0)} for name, data in self.players.items() if isinstance(data, dict)]
        return sorted(ranking, key=lambda x: x["score"], reverse=True)

    def save(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            data = self.to_dict_for_db()
            cursor.execute('''
            INSERT OR REPLACE INTO games (code, teacher_username, questions, players, status, current_question, start_time, question_start_time)
            VALUES (:code, :teacher_username, :questions, :players, :status, :current_question, :start_time, :question_start_time)
            ''', data)
            conn.commit()
        except sqlite3.Error as e:
            print(f"Erro ao salvar jogo {self.code} no SQLite: {e}")
            st.error(f"Erro de banco de dados ao salvar jogo: {e}")
        finally:
            conn.close()

    @classmethod
    def get_by_code(cls, code):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM games WHERE code = ?", (code,))
            row = cursor.fetchone()
            return cls.from_db_row(row)
        except sqlite3.Error as e:
            print(f"Erro ao buscar jogo {code} no SQLite: {e}")
            st.error(f"Erro de banco de dados ao buscar jogo por código: {e}")
            return None
        finally:
            conn.close()
    
    @classmethod
    def get_by_teacher(cls, teacher_username):
        conn = get_db_connection()
        cursor = conn.cursor()
        games_list = []
        try:
            cursor.execute("SELECT * FROM games WHERE teacher_username = ?", (teacher_username,))
            rows = cursor.fetchall()
            for row in rows:
                games_list.append(cls.from_db_row(row))
            return games_list
        except sqlite3.Error as e:
            print(f"Erro ao buscar jogos do professor {teacher_username} no SQLite: {e}")
            st.error(f"Erro de banco de dados ao buscar jogos por professor: {e}")
            return []
        finally:
            conn.close()

# SAMPLE_QUESTIONS e PLAYER_ICONS permanecem os mesmos.
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
    "question": "Um site é executado em instâncias do Amazon EC2 em um grupo de Auto Scaling atrás de um Application Load Balancer (ALB) que serve como origem para uma distribuição do Amazon CloudFront. Um AWS WAF está sendo usado para proteção contra ataques de injeção de SQL. Uma revisão dos logs de segurança revelou um IP malicioso externo que precisa ser bloqueado para acessar o site. O que um arquiteto de soluções deve fazer para proteger o aplicativo?",
    "options": [
      "Modificar a rede ACL para as instâncias do EC2 nos grupos de destino atrás do ALB para negar o endereço IP malicioso",
      "Modifique os grupos de segurança para as instâncias do EC2 nos grupos de destino por trás do ALB para negar o endereço IP malicioso",
      "Modificar a configuração do AWS WAF para adicionar uma condição de correspondência de IP para bloquear o endereço IP malicioso",
      "Modificar a Network ACL na distribuição do CloudFront para adicionar uma regra de negação para o endereço IP malicioso"
    ],
    "correct": 2
  },
  {
    "question": "Uma empresa precisa conectar sua rede de data center local a uma nova nuvem privada virtual (VPC). Há uma conexão de internet simétrica de 100 Mbps na rede do data center. A taxa de transferência de dados para um aplicativo local é de vários gigabytes por dia. O processamento será feito usando um stream do Amazon Kinesis Data Firehose. O que um arquiteto de soluções deve recomendar para obter o máximo desempenho?",
    "options": [
      "Estabeleça uma conexão AWS Site-to-Site VPN entre a rede local e a VPC. Configure o roteamento BGP entre o gateway do cliente e o gateway privado virtual. Envie dados para o Kinesis Data Firehose usando uma conexão VPN",
      "Obter um dispositivo otimizado para armazenamento do AWS Snowball Edge. Os dados devem ser copiados para o dispositivo após vários dias e enviados para a AWS para transferência acelerada para o Kinesis Data Firehose. Repita conforme necessário",
      "O Kinesis Data Firehose pode ser conectado à VPC usando o AWS PrivateLink. Instale uma conexão AWS Direct Connect de 1 Gbps entre a rede local e a AWS. Para enviar dados do local para o Kinesis Data Firehose, use o endpoint do PrivateLink",
      "Estabeleça uma conexão de emparelhamento entre a rede local e a VPC. Configure o roteamento para a rede local para usar a conexão de emparelhamento de VPC"
    ],
    "correct": 2
  },
  {
    "question": "Uma equipe de levantamento está usando uma frota de drones para coletar imagens de canteiros de obras. Os laptops da equipe de pesquisa carecem de armazenamento embutido e capacidade de computação para transferir as imagens e processar os dados. Embora a equipe tenha instâncias do Amazon EC2 para processamento e buckets do Amazon S3 para armazenamento, a conectividade de rede é intermitente e não confiável. As imagens precisam ser processadas para avaliar o andamento de cada canteiro de obras. O que um arquiteto de soluções deve recomendar?",
    "options": [
      "Configurar o Amazon Kinesis Data Firehose para criar vários fluxos de entrega direcionados separadamente para os buckets do S3 para armazenamento e as instâncias do EC2 para processar as imagens",
      "Durante a conectividade intermitente com instâncias do EC2, fazer upload de imagens para o Amazon SQS",
      "Processar e armazenar as imagens usando dispositivos AWS Snowball Edge",
      "Cache as imagens localmente em um dispositivo de hardware pré-instalado com AWS Storage Gateway para processar as imagens quando a conectividade for restaurada"
    ],
    "correct": 2
  },
  {
    "question": "Um aplicativo da Web é executado em sub-redes públicas e privadas. A arquitetura do aplicativo consiste em uma camada da web e uma camada de banco de dados em execução em instâncias do Amazon EC2. Ambas as camadas são executadas em uma única zona de disponibilidade (AZ). Qual combinação de etapas um arquiteto de soluções deve adotar para fornecer alta disponibilidade para essa arquitetura?",
    "options": [
      "Criar um grupo do Amazon EC2 Auto Scaling e um Application Load Balancer (ALB) abrangendo várias AZs",
      "Adicionar as instâncias de aplicativos Web existentes a um grupo de Auto Scaling atrás de um Application Load Balancer (ALB)",
      "Criar novas sub-redes públicas e privadas na mesma AZ para alta disponibilidade",
      "Crie novas sub-redes públicas e privadas na mesma VPC, cada uma em uma nova AZ. Migre o banco de dados para uma implantação multi-AZ do Amazon RDS"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa carregou alguns dados altamente críticos para um bucket do Amazon S3. A gerência está preocupada com a disponibilidade dos dados e exige que sejam tomadas medidas para proteger os dados contra exclusão acidental. Os dados ainda devem estar acessíveis e um usuário deve poder excluir os dados intencionalmente. Qual combinação de etapas um arquiteto de soluções deve adotar para realizar isso?",
    "options": [
      "Criar uma política de ciclo de vida para os objetos no bucket do S3",
      "Ativar exclusão de MFA no bucket do S3",
      "Criar uma política de bucket no bucket do S3",
      "Ativar versionamento no bucket do S3"
    ],
    "correct": 1
  },
  {
    "question": "Um banco de dados persistente deve ser migrado de um servidor local para uma instância do Amazon EC2. O banco de dados requer 64.000 IOPS e, se possível, deve ser armazenado em um único volume do Amazon EBS. Qual solução um Arquiteto de Soluções deve recomendar?",
    "options": [
      "Criar uma instância do Amazon EC2 com quatro volumes SSD (gp2) de uso geral do Amazon EBS anexados. Maximize o IOPS em cada volume e use um conjunto de faixas RAID 0",
      "Usar uma instância da família otimizada de E/S I3 e aproveitar o instance store para atingir o requisito de IOPS",
      "Criar uma instância do Amazon EC2 baseada em Nitro com um volume Amazon EBS Provisioned IOPS SSD (io1) anexado. Provisionar 64.000 IOPS para o volume",
      "Criar uma instância do Amazon EC2 com dois volumes Amazon EBS Provisioned IOPS SSD (io1) anexados. Provisionar 32.000 IOPS por volume e criar um volume lógico usando o SO que agrega a capacidade"
    ],
    "correct": 2
  },
  {
    "question": "Uma torre de servidores de arquivos do Microsoft Windows usa DFSR (Distributed File System Replication) para sincronizar dados em um ambiente local. A infraestrutura está sendo migrada para a Nuvem AWS. Qual serviço o arquiteto de soluções deve usar para substituir o farm de servidores de arquivos?",
    "options": [
      "Amazon EBS",
      "Amazon EFS",
      "AWS Storage Gateway",
      "Amazon FSx"
    ],
    "correct": 3
  },
  {
    "question": "Uma empresa exige que todas as contas de usuário do AWS IAM tenham requisitos específicos de complexidade e comprimento mínimo de senha. Como um Arquiteto de Soluções deve fazer isso?",
    "options": [
      "Definir uma política de senha para toda a conta da AWS",
      "Criar uma política do IAM que aplique os requisitos e aplique-os a todos os usuários",
      "Usar uma regra do AWS Config para aplicar os requisitos ao criar contas de usuário",
      "Definir uma política de senha para cada usuário do IAM na conta da AWS"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa fornece uma interface baseada em REST para um aplicativo que permite que uma empresa parceira envie dados quase em tempo real. O aplicativo então processa os dados recebidos e os armazena para análise posterior. O aplicativo é executado em instâncias do Amazon EC2. A empresa parceira recebeu muitos erros de serviço 503 indisponíveis ao enviar dados para o aplicativo e a capacidade de computação atinge seus limites e não consegue processar solicitações quando ocorrem picos no volume de dados. Qual projeto um Arquiteto de Soluções deve implementar para melhorar a escalabilidade?",
    "options": [
      "Usar o Amazon SNS para ingerir os dados e acionar funções do AWS Lambda para processar os dados quase em tempo real",
      "Usar o Amazon Kinesis Data Streams para ingerir os dados. Processar os dados usando funções do AWS Lambda",
      "Usar o Amazon API Gateway na frente do aplicativo existente. Criar um plano de uso com limite de cota para a empresa parceira",
      "Usar o Amazon SQS para ingerir os dados. Configurar as instâncias do EC2 para processar mensagens da fila do SQS"
    ],
    "correct": 1
  },
  {
    "question": "Uma réplica de leitura do Amazon RDS está sendo implantada em uma região separada. O banco de dados mestre não é criptografado, mas todos os dados na nova região devem ser criptografados. Como isso pode ser alcançado?",
    "options": [
      "Ativar criptografia usando o KMS (Key Management Service) ao criar a réplica de leitura entre regiões",
      "A criptografia habilitada na instância de banco de dados mestre e, em seguida, crie uma réplica de leitura criptografada entre regiões",
      "Criptografar um snapshot da instância de banco de dados mestre, criar uma réplica de leitura criptografada entre regiões a partir do snapshot",
      "Criptografar um snapshot da instância de banco de dados mestre, criar uma nova instância de banco de dados mestre criptografada e, em seguida, criar uma réplica de leitura criptografada entre regiões"
    ],
    "correct": 3
  },
  {
    "question": "Um aplicativo da web permite que os usuários façam upload de fotos e adicionem elementos gráficos a elas. O aplicativo oferece dois níveis de serviço: gratuito e pago. As fotos enviadas por usuários pagos devem ser processadas antes daquelas enviadas usando o nível gratuito. As fotos são carregadas em um bucket do Amazon S3 que usa uma notificação de evento para enviar as informações do trabalho ao Amazon SQS. Como um arquiteto de soluções deve configurar a implantação do Amazon SQS para atender a esses requisitos?",
    "options": [
      "Use uma fila SQS FIFO separada para cada camada. Defina a fila livre para usar sondagem curta e a fila paga para usar sondagem longa",
      "Usar uma fila SQS FIFO. Atribuir uma prioridade mais alta às fotos pagas para que sejam processadas primeiro",
      "Usar uma fila padrão SQS. Usar lotes para fotos pagas e pesquisa curta para fotos gratuitas",
      "Use uma fila SQS Standard separada para cada camada. Configure as instâncias do Amazon EC2 para priorizar a sondagem da fila paga sobre a fila gratuita"
    ],
    "correct": 3
  },
  {
    "question": "Uma empresa executa um aplicativo que usa um banco de dados PostgreSQL do Amazon RDS. O banco de dados não está criptografado no momento. Um Arquiteto de Soluções foi instruído que, devido aos novos requisitos de conformidade, todos os dados existentes e novos no banco de dados devem ser criptografados. O banco de dados sofre grandes volumes de alterações e nenhum dado pode ser perdido. Como o Arquiteto de Soluções pode habilitar a criptografia para o banco de dados sem incorrer em perda de dados?",
    "options": [
      "Crie um snapshot da instância de banco de dados RDS existente. Crie uma cópia criptografada do snapshot. Crie uma nova instância de banco de dados RDS a partir do snapshot criptografado. Configure o aplicativo para usar o novo endpoint de banco de dados",
      "Criar uma réplica de leitura RDS e especificar uma chave de criptografia. Promover a réplica de leitura criptografada a primária. Atualizar o aplicativo para apontar para o novo endpoint de banco de dados RDS",
      "Crie um snapshot da instância de banco de dados RDS existente. Crie uma cópia criptografada do snapshot. Crie uma nova instância de banco de dados RDS a partir do snapshot criptografado e atualize o aplicativo. Use o AWS DMS para sincronizar dados entre os bancos de dados RDS de origem e destino",
      "Atualize o banco de dados RDS para o modo Multi-AZ e habilite a criptografia para a réplica em espera. Execute um failover para a instância em espera e exclua a instância de banco de dados RDS não criptografada"
    ],
    "correct": 2
  },
  {
    "question": "O aplicativo da web de uma empresa está usando várias instâncias Linux do Amazon EC2 e armazenando dados em volumes do Amazon EBS. A empresa está procurando uma solução para aumentar a resiliência do aplicativo em caso de falha. O que um arquiteto de soluções deve fazer para atender a esses requisitos?",
    "options": [
      "Criar um Application Load Balancer com grupos de Auto Scaling em várias zonas de disponibilidade. Armazenar dados usando Amazon S3 One Zone- Infrequent Access (S3 One Zone-IA)",
      "Crie um Application Load Balancer com grupos de Auto Scaling em várias zonas de disponibilidade. Armazene dados no Amazon EFS e monte um destino em cada instância",
      "Criar um Application Load Balancer com grupos de Auto Scaling em várias zonas de disponibilidade. Montar um instance store em cada instância do EC2",
      "Iniciar o aplicativo em instâncias do EC2 em cada zona de disponibilidade. Anexar volumes do EBS a cada instância do EC2"
    ],
    "correct": 1
  },
  {
    "question": "Um arquiteto de soluções está criando um aplicativo de envio de documentos para uma escola. O aplicativo usará um bucket do Amazon S3 para armazenamento. A solução deve evitar a exclusão acidental dos documentos e garantir que todas as versões dos documentos estejam disponíveis. Os usuários devem poder fazer upload e modificar os documentos. Que combinação de ações deve ser tomada para atender a esses requisitos?",
    "options": [
      "Criptografar o bucket usando AWS SSE-S3",
      "Definir permissões somente leitura no bucket",
      "Ativar exclusão de MFA no bucket",
      "Ativar versionamento no bucket"
    ],
    "correct": 3
  },
  {
    "question": "Uma empresa de comércio eletrônico executa um aplicativo em instâncias do Amazon EC2 em sub-redes públicas e privadas. O aplicativo Web é executado em uma sub-rede pública e o banco de dados é executado em uma sub-rede privada. As sub-redes públicas e privadas estão em uma única zona de disponibilidade. Qual combinação de etapas um arquiteto de soluções deve adotar para fornecer alta disponibilidade para essa arquitetura?",
    "options": [
      "Criar um grupo do EC2 Auto Scaling na sub-rede pública e usar um Application Load Balancer",
      "Criar novas sub-redes públicas e privadas em uma AZ diferente. Migrar o banco de dados para uma implantação multi-AZ do Amazon RDS",
      "Criar novas sub-redes públicas e privadas na mesma AZ, mas em uma Amazon VPC diferente",
      "Criar um grupo do EC2 Auto Scaling e o Application Load Balancer que se estende por várias AZs"
    ],
    "correct": 1
  },
  {
    "question": "Uma empresa executa um aplicativo em uma instância do Amazon EC2 que requer 250 GB de espaço de armazenamento. O aplicativo não é usado com frequência e apresenta pequenos picos de uso nas manhãs e tardes dos dias úteis. A E/S de disco pode variar com picos atingindo um máximo de 3.000 IOPS. Um Arquiteto de Soluções deve recomendar a solução de armazenamento mais econômica que ofereça o desempenho necessário. Qual configuração o Arquiteto de Soluções deve recomendar?",
    "options": [
      "Amazon EBS Throughput Optimized HDD (st1)",
      "Amazon EBS Cold HDD (sc1)",
      "Amazon EBS Provisioned IOPS SSD (io1)",
      "Amazon EBS General Purpose SSD (gp2)"
    ],
    "correct": 3
  },
  {
    "question": "Uma empresa de serviços financeiros tem um aplicativo da Web com uma camada de aplicativo em execução nos EUA e na Europa. A camada de banco de dados consiste em um banco de dados MySQL em execução no Amazon EC2 em us-west-1. Os usuários são direcionados para a camada de aplicativo mais próxima usando o roteamento baseado em latência do Route 53. Os usuários na Europa relataram baixo desempenho ao executar consultas. Quais mudanças um Arquiteto de Soluções deve fazer na camada de banco de dados para melhorar o desempenho?",
    "options": [
      "Migrar o banco de dados para o Amazon RDS for MySQL. Configurar o Multi- AZ em uma das regiões europeias",
      "Migrar o banco de dados para o Amazon RedShift. Use o AWS DMS para sincronizar dados. Configurar aplicativos para usar o data warehouse do RedShift para consultas",
      "Criar uma réplica de leitura do Amazon RDS em uma das regiões europeias. Configurar o nível do aplicativo na Europa para usar a réplica de leitura para consultas",
      "Migrar o banco de dados para um banco de dados global do Amazon Aurora no modo de compatibilidade do MySQL. Configurar a camada do aplicativo na Europa para usar o endpoint do leitor local"
    ],
    "correct": 3
  },
  {
    "question": "Uma empresa está migrando de uma infraestrutura local para a Nuvem AWS. Um dos aplicativos da empresa armazena arquivos em um farm de servidores de arquivos do Windows que usa DFSR (Distributed File System Replication) para manter os dados sincronizados. Um arquiteto de soluções precisa substituir o farm de servidores de arquivos. Qual serviço o arquiteto de soluções deve usar?",
    "options": [
      "Amazon EFS",
      "AWS Storage Gateway",
      "Amazon S3",
      "Amazon FSx"
    ],
    "correct": 3
  },
  {
    "question": "Um arquiteto de soluções precisa fazer backup de alguns arquivos de log de aplicativos de uma loja de comércio eletrônico online para o Amazon S3. Não se sabe com que frequência os logs serão acessados ou quais logs serão mais acessados. O arquiteto de soluções deve manter os custos tão baixos quanto possível usando a classe de armazenamento S3 apropriada. Qual classe de armazenamento do S3 deve ser implementada para atender a esses requisitos?",
    "options": [
      "S3 Intelligent-Tiering",
      "S3 One Zone-Infrequent Access (S3 One Zone-IA)",
      "S3 Glacier",
      "S3 Standard-Infrequent Access (S3 Standard-IA)"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa deseja restringir o acesso à tabela do Amazon DynamoDB a endereços IP de origem privada específicos de sua VPC. O que deve ser feito para garantir o acesso à mesa?",
    "options": [
      "Criar um VPC endpoint de gateway e adicionar uma entrada à tabela de rotas",
      "Criar a tabela do Amazon DynamoDB na VPC",
      "Criar um VPC endpoint de interface na VPC com uma Elastic Network Interface (ENI)",
      "Criar uma conexão VPN da AWS com o endpoint do Amazon DynamoDB"
    ],
    "correct": 0
  },
  {
    "question": "A capacidade de armazenamento tornou-se um problema para uma empresa que executa servidores de aplicativos no local. Os servidores são conectados a uma combinação de armazenamento em bloco e soluções de armazenamento NFS. A empresa exige uma solução que suporte o armazenamento em cache local sem rearquitetar seus aplicativos existentes. Que combinação de mudanças a empresa pode fazer para atender a esses requisitos?",
    "options": [
      "Usar um Volume Gateway do AWS Storage Gateway para substituir o armazenamento em bloco",
      "Usar o comando mount em servidores para montar buckets do Amazon S3 usando NFS",
      "Usar um File Gateway do AWS Storage Gateway para substituir o armazenamento NFS",
      "Usar AWS Direct Connect e montar um Amazon FSx for Windows File Server usando iSCSI"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa possui duas contas para realizar testes e cada conta possui uma única VPC: VPC-TEST1 e VPC-TEST2. A equipe de operações exige um método de cópia segura de arquivos entre instâncias do Amazon EC2 nessas VPCs. A conectividade não deve ter pontos únicos de falha ou restrições de largura de banda. Qual solução um Arquiteto de Soluções deve recomendar?",
    "options": [
      "Criar uma conexão de emparelhamento de VPC entre VPC-TEST1 e VPC-TEST2",
      "Anexar um gateway privado virtual ao VPC-TEST1 e VPC-TEST2 e habilitar o roteamento",
      "Anexar um gateway Direct Connect ao VPC-TEST1 e VPC-TEST2 e habilitar o roteamento",
      "Criar um VPC gateway endpoint para cada instância do EC2 e atualizar as tabelas de rotas"
    ],
    "correct": 0
  },
  {
    "question": "Uma organização tem uma grande quantidade de dados em compartilhamentos de arquivos do Windows (SMB) em seu data center local. A organização gostaria de mover dados para o Amazon S3. Eles gostariam de automatizar a migração de dados pelo link do AWS Direct Connect. Qual serviço da AWS pode ajudá-los?",
    "options": [
      "AWS Snowball",
      "AWS CloudFormation",
      "AWS DataSync",
      "AWS Database Migration Service (DMS)"
    ],
    "correct": 2
  },
  {
    "question": "Uma empresa entrega conteúdo para assinantes distribuídos globalmente a partir de um aplicativo executado na AWS. O aplicativo usa uma frota de instâncias do Amazon EC2 em uma sub-rede privada atrás de um Application Load Balancer (ALB). Devido a uma atualização nas restrições de direitos autorais, é necessário bloquear o acesso para países específicos. Qual é o método MAIS FÁCIL para atender a esse requisito?",
    "options": [
      "Modificar o grupo de segurança ALB para negar tráfego de entrada de países bloqueados",
      "Modificar o grupo de segurança para instâncias do EC2 para negar tráfego de entrada de países bloqueados",
      "Usar o Amazon CloudFront para servir o aplicativo e negar acesso a países bloqueados",
      "Usar uma Network ACL para bloquear os intervalos de endereços IP associados a países específicos"
    ],
    "correct": 2
  },
  {
    "question": "Uma empresa implantou um novo site em instâncias do Amazon EC2 por trás de um Application Load Balancer (ALB). O Amazon Route 53 é usado para o serviço DNS. A empresa pediu a um Arquiteto de Soluções para criar um site de backup com detalhes de contato de suporte para os quais os usuários serão direcionados automaticamente se o site principal estiver inativo. Como o Arquiteto de Soluções deve implantar essa solução de forma econômica?",
    "options": [
      "Configurar um site estático usando o Amazon S3 e criar uma política de roteamento de failover do Route 53",
      "Criar o site de backup no EC2 e no ALB em outra região e criar um endpoint do AWS Global Accelerator",
      "Configurar um site estático usando o Amazon S3 e criar uma política de roteamento ponderado do Route 53",
      "Implantar o site de backup no EC2 e ALB em outra região e usar as verificações de integridade do Route 53 para roteamento de failover"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa de varejo com muitas lojas e armazéns está implementando sensores de IoT para coletar dados de monitoramento de dispositivos em cada local. Os dados serão enviados à AWS em tempo real. Um arquiteto de soluções deve fornecer uma solução para garantir que os eventos sejam recebidos em ordem para cada dispositivo e garantir que os dados sejam salvos para processamento futuro. Qual solução seria MAIS eficiente?",
    "options": [
      "Usar o Amazon Kinesis Data Streams para eventos em tempo real com uma chave de partição para cada dispositivo. Usar o Amazon Kinesis Data Firehose para salvar dados no Amazon S3",
      "Usar uma fila padrão do Amazon SQS para eventos em tempo real com uma fila para cada dispositivo. Acionar uma função do AWS Lambda da fila do SQS para salvar dados no Amazon S3",
      "Usar uma fila FIFO do Amazon SQS para eventos em tempo real com uma fila para cada dispositivo. Acionar uma função do AWS Lambda para a fila do SQS para salvar dados no Amazon EFS",
      "Usar o Amazon Kinesis Data Streams para eventos em tempo real com um estilhaço para cada dispositivo. Usar o Amazon Kinesis Data Firehose para salvar dados no Amazon EBS"
    ],
    "correct": 0
  },
  {
    "question": "Um novo aplicativo será executado em várias tarefas do Amazon ECS. A lógica do aplicativo de front-end processará os dados e, em seguida, passará esses dados para uma tarefa ECS de back-end para realizar processamento adicional e gravar os dados em um banco de dados. O Arquiteto gostaria de reduzir as interdependências para que as falhas não afetem outros componentes. Qual solução o Arquiteto deve usar?",
    "options": [
      "Criar um stream do Amazon Kinesis Firehose que entrega dados a um bucket do Amazon S3, configurar o front-end para gravar dados no stream e o back-end para ler dados do Amazon S3",
      "Criar uma fila do Amazon SQS e configurar o front-end para adicionar mensagens à fila e o back-end para ler a fila em busca de mensagens",
      "Criar uma fila do Amazon SQS que envia mensagens para o back-end. Configure o front-end para adicionar mensagens à fila",
      "Criar um stream do Amazon Kinesis Firehose e configurar o front-end para adicionar dados ao stream e o back-end para ler os dados do stream"
    ],
    "correct": 1
  },
  {
    "question": "Uma empresa executa um aplicativo em um data center local que coleta dados ambientais do maquinário de produção. Os dados consistem em arquivos JSON armazenados no armazenamento conectado à rede (NAS) e cerca de 5 TB de dados são coletados a cada dia. A empresa deve fazer upload desses dados para o Amazon S3, onde podem ser processados por um aplicativo de análise. Os dados devem ser transferidos com segurança. Qual solução oferece a transferência de dados MAIS confiável e eficiente em termos de tempo?",
    "options": [
      "Amazon S3 Transfer Acceleration pela Internet",
      "Serviço de migração de banco de dados da AWS pela Internet",
      "AWS DataSync com AWS Direct Connect",
      "Vários dispositivos AWS Snowcone"
    ],
    "correct": 2
  },
  {
    "question": "Uma produtora de vídeo está planejando migrar algumas de suas cargas de trabalho para a Nuvem AWS. A empresa exigirá cerca de 5 TB de armazenamento para processamento de vídeo com o máximo desempenho de E/S possível. Eles também exigem mais de 400 TB de armazenamento extremamente durável para armazenar arquivos de vídeo e 800 TB de armazenamento para arquivamento de longo prazo. Quais combinações de serviços um Arquiteto de Soluções deve usar para atender a esses requisitos?",
    "options": [
      "Amazon EC2 instance store para desempenho máximo, Amazon S3 para armazenamento de dados durável e Amazon S3 Glacier para armazenamento de arquivamento de longo prazo",
      "Amazon EC2 instance store para desempenho máximo, Amazon EFS para armazenamento de dados durável e Amazon S3 para armazenamento de arquivamento de longo prazo",
      "Amazon EBS para desempenho máximo, Amazon S3 para armazenamento de dados durável e Amazon S3 Glacier para armazenamento de arquivamento de longo prazo",
      "Amazon EBS para desempenho máximo, Amazon EFS para armazenamento de dados durável e Amazon S3 Glacier para armazenamento de arquivamento de longo prazo"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa está implantando uma frota de instâncias do Amazon EC2 executando Linux em várias zonas de disponibilidade em uma região da AWS. O aplicativo requer uma solução de armazenamento de dados que possa ser acessada por todas as instâncias do EC2 simultaneamente. A solução deve ser altamente escalável e fácil de implementar. O armazenamento deve ser montado usando o protocolo NFS. Qual solução atende a esses requisitos?",
    "options": [
      "Criar um volume do Amazon EBS e usar o EBS Multi-Attach para montar o volume em todas as instâncias do EC2 em cada zona de disponibilidade",
      "Crie um sistema de arquivos do Amazon EFS com destinos de montagem em cada zona de disponibilidade. Configure as instâncias do aplicativo para montar o sistema de arquivos",
      "Criar um bucket do Amazon S3 e criar um gateway endpoint do S3 para permitir acesso ao sistema de arquivos usando o protocolo NFS",
      "Crie um banco de dados do Amazon RDS e armazene os dados em um formato BLOB. Aponte as instâncias do aplicativo para o endpoint RDS"
    ],
    "correct": 1
  },
  {
    "question": "O aplicativo de uma empresa está sendo executado em instâncias do Amazon EC2 em uma única região. No caso de um desastre, um arquiteto de soluções precisa garantir que os recursos também possam ser implantados em uma segunda região. Qual combinação de ações o arquiteto de soluções deve tomar para conseguir isso?",
    "options": [
      "Iniciar uma nova instância do EC2 na segunda região e copiar um volume do Amazon S3 para a nova instância",
      "Copiar uma imagem de máquina da Amazon (AMI) de uma instância do EC2 e especificar a segunda região para o destino",
      "Desanexar um volume de uma instância do EC2 e copiá-lo para um bucket do Amazon S3 na segunda região",
      "Iniciar uma nova instância do EC2 de uma Amazon Machine Image (AMI) na segunda região"
    ],
    "correct": 1
  },
  {
    "question": "Uma empresa oferece uma panfleto de produto online que é entregue a partir de um site estático em execução no Amazon S3. Os clientes da empresa estão principalmente nos Estados Unidos, Canadá e Europa. A empresa está procurando reduzir a latência de maneira econômica para usuários nessas regiões. Qual é a solução mais econômica para esses requisitos?",
    "options": [
      "Criar uma distribuição do Amazon CloudFront e definir a classe de preço para usar todos os pontos de presença para obter melhor desempenho",
      "Crie uma distribuição do Amazon CloudFront e defina a classe de preço para usar apenas EUA, Canadá e Europa.",
      "Criar uma distribuição do Amazon CloudFront que usa origens nos EUA, Canadá e Europa",
      "Criar uma distribuição do Amazon CloudFront e usar o Lambda@Edge para executar o processamento de dados do site mais próximo dos usuários"
    ],
    "correct": 1
  },
  {
    "question": "Um aplicativo de comércio eletrônico consiste em três camadas. A camada da web inclui instâncias do EC2 por trás de um balanceador de carga, a camada intermediária usa instâncias do EC2 e uma fila do Amazon SQS para processar pedidos e a camada de banco de dados consiste em uma tabela do Auto Scaling DynamoDB. Durante os períodos de maior movimento, os clientes reclamaram de atrasos no processamento de pedidos. Um Arquiteto de Soluções foi encarregado de reduzir os tempos de processamento. Qual ação será MAIS eficaz para cumprir esse requisito?",
    "options": [
      "Adicionar uma distribuição do Amazon CloudFront com uma origem personalizada para armazenar em cache as respostas para a camada da web",
      "Substituir a fila do Amazon SQS pelo Amazon Kinesis Data Firehose",
      "Usar Amazon EC2 Auto Scaling para dimensionar as instâncias de camada intermediária com base na profundidade da fila SQS",
      "Usar o Amazon DynamoDB Accelerator (DAX) na frente da camada de back-end do DynamoDB"
    ],
    "correct": 2
  },
  {
    "question": "Uma empresa hospeda um aplicativo em instâncias do Amazon EC2 por trás de Application Load Balancers em várias regiões da AWS. Os direitos de distribuição do conteúdo exigem que os usuários em diferentes geografias recebam conteúdo de regiões específicas. Qual configuração atende a esses requisitos?",
    "options": [
      "Criar registros do Amazon Route 53 com uma política de roteamento de geoproximidade",
      "Configurar Application Load Balancers com roteamento multirregional",
      "Configurar o Amazon CloudFront com várias origens e AWS WAF",
      "Criar registros do Amazon Route 53 com uma política de roteamento de geolocalização"
    ],
    "correct": 3
  },
  {
    "question": "Está sendo criado um aplicativo que usará instâncias do Amazon EC2 para gerar e armazenar dados. Outro conjunto de instâncias do EC2 analisará e modificará os dados. Os requisitos de armazenamento serão significativos e continuarão a crescer ao longo do tempo. Os arquitetos de aplicativos exigem uma solução de armazenamento. Quais ações atenderiam a essas necessidades?",
    "options": [
      "Armazenar os dados no AWS Storage Gateway. Configurar o AWS Direct Connect entre o dispositivo Gateway e as instâncias do EC2",
      "Armazenar os dados no Amazon S3 Glacier. Atualizar a política de cofre para permitir o acesso às instâncias do aplicativo",
      "Armazene os dados em um sistema de arquivos do Amazon EFS. Monte o sistema de arquivos nas instâncias do aplicativo",
      "Armazenar os dados em um volume do Amazon EBS. Montar o volume do EBS nas instâncias do aplicativo"
    ],
    "correct": 2
  },
  {
    "question": "Um arquiteto de soluções implantou um aplicativo em várias instâncias do Amazon EC2 em três sub-redes privadas. O aplicativo deve ser disponibilizado para clientes baseados na Internet com o mínimo de esforço administrativo. Como o Arquiteto de Soluções pode disponibilizar o aplicativo na internet?",
    "options": [
      "Criar um gateway NAT em uma sub-rede pública. Adicionar uma rota ao gateway NAT às tabelas de rotas das três sub-redes privadas",
      "Crie um Application Load Balancer e associe três sub-redes públicas das mesmas zonas de disponibilidade que as instâncias privadas. Adicione as instâncias privadas ao ALB",
      "Criar uma Amazon Machine Image (AMI) das instâncias na sub-rede privada e executar novas instâncias da AMI em sub-redes públicas. Criar um Application Load Balancer e adicionar as instâncias públicas ao ALB",
      "Crie um Application Load Balancer e associe três sub-redes privadas das mesmas zonas de disponibilidade que as instâncias privadas. Adicionar as instâncias privadas ao ALB"
    ],
    "correct": 1
  },
  {
    "question": "Uma organização da AWS tem uma unidade organizacional (UO) com várias contas-membro. A empresa precisa restringir a capacidade de executar apenas tipos específicos de instância do Amazon EC2. Como essa política pode ser aplicada nas contas com o mínimo de esforço?",
    "options": [
      "Criar um SCP com uma regra de negação que negue todos, exceto os tipos de instância específicos",
      "Criar uma política do IAM para negar a execução de todos, exceto os tipos de instância específicos",
      "Usar o AWS Resource Access Manager para controlar quais tipos de execução podem ser usados",
      "Criar um SCP com uma regra de permissão que permita iniciar os tipos de instância específicos"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa planeja tornar uma instância Linux do Amazon EC2 indisponível fora do horário comercial para economizar custos. A instância é apoiada por um volume do Amazon EBS. Há um requisito de que o conteúdo da memória da instância deve ser preservado quando ela se torna indisponível. Como um arquiteto de soluções pode atender a esses requisitos?",
    "options": [
      "Usar o Auto Scaling para reduzir a instância fora do horário comercial. Expandir a instância quando necessário",
      "Encerrar a instância fora do horário comercial. Recupere a instância novamente quando necessário",
      "Parar a instância fora do horário comercial. Iniciar a instância novamente quando necessário",
      "Hibernar a instância fora do horário comercial. Iniciar a instância novamente quando necessário"
    ],
    "correct": 3
  },
  {
    "question": "Uma empresa está trabalhando com um parceiro estratégico que possui um aplicativo que deve ser capaz de enviar mensagens para uma das filas do Amazon SQS da empresa. A empresa parceira tem sua própria conta da AWS. Como um Arquiteto de Soluções pode fornecer acesso com privilégios mínimos ao parceiro?",
    "options": [
      "Atualizar a política de permissão na fila do SQS para conceder todas as permissões à conta da AWS do parceiro",
      "Criar uma função entre contas com acesso a todas as filas do SQS e usar a conta da AWS do parceiro no documento de confiança para a função",
      "Atualize a política de permissão na fila do SQS para conceder a permissão sqs:SendMessage à conta da AWS do parceiro",
      "Crie uma conta de usuário e conceda a permissão sqs:SendMessage para o Amazon SQS. Compartilhe as credenciais com a empresa parceira"
    ],
    "correct": 2
  },
  {
    "question": "Uma empresa executa um aplicativo em seis servidores de aplicativos web em um grupo do Amazon EC2 Auto Scaling em uma única zona de disponibilidade. O aplicativo é liderado por um Application Load Balancer (ALB). Um Arquiteto de Soluções precisa modificar a infraestrutura para ter alta disponibilidade sem fazer nenhuma modificação no aplicativo. Qual arquitetura o Arquiteto de Soluções deve escolher para habilitar a alta disponibilidade?",
    "options": [
      "Criar uma distribuição do Amazon CloudFront com uma origem personalizada em várias regiões",
      "Modificar o grupo de Auto Scaling para usar duas instâncias em cada uma das três zonas de disponibilidade",
      "Criar um grupo de Auto Scaling para executar três instâncias em cada uma das duas regiões",
      "Criar um modelo de execução que possa ser usado para criar rapidamente mais instâncias em outra região"
    ],
    "correct": 1
  },
  {
    "question": "Uma empresa está investigando métodos para reduzir as despesas associadas à infraestrutura de backup no local. O Arquiteto de Soluções deseja reduzir custos eliminando o uso de fitas físicas de backup. É um requisito que os aplicativos e fluxos de trabalho de backup existentes continuem funcionando. O que o Arquiteto de Soluções deve recomendar?",
    "options": [
      "Criar um sistema de arquivos do Amazon EFS e conectar os aplicativos de backup usando o protocolo NFS",
      "Conectar os aplicativos de backup a um AWS Storage Gateway usando uma biblioteca de fitas virtuais iSCSI (VTL)",
      "Criar um sistema de arquivos do Amazon EFS e conectar os aplicativos de backup usando o protocolo iSCSI",
      "Conectar os aplicativos de backup a um AWS Storage Gateway usando o protocolo NFS"
    ],
    "correct": 1
  },
  {
    "question": "Uma companhia de seguros tem um aplicativo da web que atende usuários no Reino Unido e na Austrália. O aplicativo inclui uma camada de banco de dados usando um banco de dados MySQL hospedado em eu-west-2. A camada da web é executada de eu-west-2 e ap-southeast-2. O roteamento de geoproximidade do Amazon Route 53 é usado para direcionar os usuários para a camada da web mais próxima. Observou-se que os usuários australianos recebem tempos de resposta lentos às consultas. Quais alterações devem ser feitas na camada de banco de dados para melhorar o desempenho?",
    "options": [
      "Migrar o banco de dados para o Amazon RDS for MySQL. Configurar Multi-AZ na região australiana",
      "Migrar o banco de dados para um banco de dados global do Amazon Aurora no modo de compatibilidade do MySQL. Configurar réplicas de leitura em ap-southeast-2",
      "Implantar instâncias do MySQL em cada região. Implantar um Application Load Balancer na frente do MySQL para reduzir a carga na instância primária",
      "Migrar o banco de dados para o Amazon DynamoDB. Usar tabelas globais do DynamoDB para habilitar a replicação para regiões adicionais"
    ],
    "correct": 1
  },
  {
    "question": "Uma empresa executa um grande trabalho de processamento em lote no final de cada trimestre. O trabalho de processamento é executado por 5 dias e usa 15 instâncias do Amazon EC2. O processamento deve ser executado ininterruptamente por 5 horas por dia. A empresa está investigando maneiras de reduzir o custo do trabalho de processamento em lote. Qual modelo de precificação a empresa deve escolher?",
    "options": [
      "Instâncias dedicadas",
      "Instâncias spot",
      "Instâncias sob demanda",
      "Instâncias reservadas"
    ],
    "correct": 2
  },
  {
    "question": "Um aplicativo herdado de computação de alto desempenho (HPC) herdado será migrado para a AWS. Qual tipo de adaptador de rede deve ser usado?",
    "options": [
      "Adaptador de rede elástica (Elastic Network Adapter/ENA)",
      "Adaptador de tecido elástico (Elastic Fabric Adapter/EFA)",
      "Endereço IP elástico",
      "Interface de rede elástico (Elastic Network Interface/ENI)"
    ],
    "correct": 1
  },
  {
    "question": "Uma empresa usa contêineres do Docker para muitas cargas de trabalho de aplicativos em um data center local. A empresa está planejando implantar contêineres na AWS e o arquiteto-chefe determinou que a mesma configuração e ferramentas administrativas sejam usadas em todos os ambientes conteinerizados. A empresa também deseja permanecer agnóstica à nuvem para proteger a mitigação do impacto de futuras mudanças na estratégia de nuvem. Como um Arquiteto de Soluções pode projetar uma solução gerenciada que se alinhe ao software de código aberto?",
    "options": [
      "Iniciar os contêineres no Amazon Elastic Container Service (ECS) com nós de trabalho da instância do Amazon EC2",
      "Iniciar os contêineres em uma frota de instâncias do Amazon EC2 em um grupo de posicionamento de cluster",
      "Iniciar os contêineres no Amazon Elastic Container Service (ECS) com instâncias do AWS Fargate",
      "Iniciar os contêineres no Amazon Elastic Kubernetes Service (EKS) e nós de trabalho do EKS"
    ],
    "correct": 3
  },
  {
    "question": "Uma empresa executa um aplicativo da Web que fornece atualizações meteorológicas. O aplicativo é executado em uma frota de instâncias do Amazon EC2 em um grupo de escalabilidade automática Multi-AZ atrás de um Application Load Balancer (ALB). As instâncias armazenam dados em um banco de dados do Amazon Aurora. Um arquiteto de soluções precisa tornar o aplicativo mais resiliente a aumentos esporádicos nas taxas de solicitação. Qual arquitetura o arquiteto de soluções deve implementar?",
    "options": [
      "Adicionar uma distribuição do Amazon CloudFront na frente do ALB",
      "Adicionar um endpoint do AWS Global Accelerator",
      "Adicionar réplicas do Amazon Aurora",
      "Adicionar e AWS WAF na frente do ALB"
    ],
    "correct": 0
  },
  {
    "question": "Um bucket do Amazon S3 na região us-east-1 hospeda o conteúdo estático do site de uma empresa. O conteúdo é disponibilizado por meio de uma origem do Amazon CloudFront apontando para esse bucket. Uma segunda cópia do bucket é criada na região ap-southeast-1 usando a replicação entre regiões. O arquiteto chefe de soluções quer uma solução que proporcione maior disponibilidade para o site. Qual combinação de ações um arquiteto de soluções deve adotar para aumentar a disponibilidade?",
    "options": [
      "Adicionar uma origem para ap-southeast-1 ao CloudFront",
      "Criar um registro no Amazon Route 53 apontando para o bucket de réplica",
      "Configurar roteamento de failover no Amazon Route 53",
      "Usando us-east-1 bucket como bucket primário e ap-southeast-1 bucket como bucket secundário, crie um grupo de origem do CloudFront"
    ],
    "correct": 0
  },
  {
    "question": "Um arquiteto de soluções está projetando a infraestrutura para executar um aplicativo em instâncias do Amazon EC2. O aplicativo requer alta disponibilidade e deve ser dimensionado dinamicamente com base na demanda para ser econômico. O que o arquiteto de soluções deve fazer para atender a esses requisitos?",
    "options": [
      "Configurar um Application Load Balancer na frente de um grupo de Auto Scaling para implantar instâncias em várias zonas de disponibilidade",
      "Configurar uma API do Amazon API Gateway na frente de um grupo de Auto Scaling para implantar instâncias em várias zonas de disponibilidade",
      "Configurar uma distribuição do Amazon CloudFront na frente de um grupo de Auto Scaling para implantar instâncias em várias regiões",
      "Configurar um Application Load Balancer na frente de um grupo de Auto Scaling para implantar instâncias em várias regiões"
    ],
    "correct": 0
  },
  {
    "question": "Um arquiteto de soluções está projetando um novo serviço que usará uma API do Amazon API Gateway no front-end. O serviço precisará persistir dados em um banco de dados de back-end usando um banco de dados de chave-valor. Inicialmente, os requisitos de dados serão em torno de 1 GB e o crescimento futuro é desconhecido. As solicitações podem variar de 0 a mais de 800 solicitações por segundo. Qual combinação de serviços da AWS atenderia a esses requisitos?",
    "options": [
      "AWS Fargate",
      "AWS Lambda",
      "Amazon DynamoDB",
      "Amazon EC2 Auto Scaling"
    ],
    "correct": 1
  },
  {
    "question": "Uma equipe está planejando executar tarefas de análise em arquivos de log todos os dias e precisa de uma solução de armazenamento. O tamanho e o número de logs são desconhecidos e os dados persistirão por apenas 24 horas. Qual é a solução mais econômica?",
    "options": [
      "Amazon S3 Standard",
      "Amazon S3 Glacier Deep Archive",
      "Amazon S3 One Zone-Infrequent Access (S3 One Zone-IA)",
      "Amazon S3 Intelligent-Tiering"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa executa um aplicativo em uma fábrica que possui um pequeno rack de recursos físicos de computação. O aplicativo armazena dados em um dispositivo de armazenamento conectado à rede (NAS) usando o protocolo NFS. A empresa exige um backup externo diário dos dados do aplicativo. Qual solução um Arquiteto de Soluções pode recomendar para atender a esse requisito?",
    "options": [
      "Usar um Volume Gateway do AWS Storage Gateway com volumes armazenados em cache no local para replicar os dados para o Amazon S3",
      "Usar um dispositivo de hardware de File Gateway do AWS Storage Gateway no local para replicar os dados para o Amazon S3",
      "Usar um Volume Gateway do AWS Storage Gateway com volumes armazenados no local para replicar os dados para o Amazon S3",
      "Criar uma VPN IPSec para AWS e configurar o aplicativo para montar o sistema de arquivos do Amazon EFS. Executar uma tarefa de cópia para fazer backup dos dados no EFS"
    ],
    "correct": 1
  },
  {
    "question": "Um arquiteto de soluções está criando um sistema que executará análises de dados financeiros por várias horas por noite, 5 dias por semana. Espera-se que a análise seja executada pela mesma duração e não possa ser interrompida depois de iniciada. O sistema será necessário por um período mínimo de 1 ano. O que o arquiteto de soluções deve configurar para garantir que as instâncias do EC2 estejam disponíveis quando forem necessárias?",
    "options": [
      "Instâncias reservadas regionais",
      "Instâncias sob demanda",
      "Reservas de capacidade sob demanda",
      "Savings Plans"
    ],
    "correct": 2
  },
  {
    "question": "Uma empresa administra um site dinâmico hospedado em um servidor local nos Estados Unidos. A empresa está se expandindo para a Europa e está investigando como pode otimizar o desempenho do site para usuários europeus. O suporte do site deve permanecer nos Estados Unidos. A empresa exige uma solução que possa ser implementada em poucos dias. O que um Arquiteto de Soluções deve recomendar?",
    "options": [
      "Migrar o site para o Amazon S3. Usar replicação entre regiões entre regiões e uma política do Route 53 baseada em latência",
      "Iniciar uma instância do Amazon EC2 em uma região da AWS nos Estados Unidos e migrar o site para ela",
      "Usar o Amazon CloudFront com uma origem personalizada apontando para os servidores locais",
      "Usar o Amazon CloudFront com Lambda@Edge para direcionar o tráfego para uma origem local"
    ],
    "correct": 2
  },
  {
    "question": "Um aplicativo executado em uma instância de contêiner do Amazon ECS usando o tipo de execução do EC2 precisa de permissões para gravar dados no Amazon DynamoDB. Como você pode atribuir essas permissões apenas à tarefa específica do ECS que está executando o aplicativo?",
    "options": [
      "Crie uma política do IAM com permissões para o DynamoDB e atribua-a a uma tarefa usando o parâmetro taskRoleArn",
      "Modificar a política AmazonECSTaskExecutionRolePolicy para adicionar permissões para o DynamoDB",
      "Criar uma política do IAM com permissões para o DynamoDB e anexá-la à instância de contêiner",
      "Usar um grupo de segurança para permitir conexões de saída ao DynamoDB e atribuí-lo à instância de contêiner"
    ],
    "correct": 0
  },
  {
    "question": "Um desenvolvedor criou um aplicativo que usa o Amazon EC2 e uma instância de banco de dados MySQL do Amazon RDS. O desenvolvedor armazenou o nome de usuário e a senha do banco de dados em um arquivo de configuração no volume raiz do EBS da instância do aplicativo EC2. Um arquiteto de soluções foi solicitado a projetar uma solução mais segura. O que o Arquiteto de Soluções deve fazer para atender a esse requisito?",
    "options": [
      "Criar uma função do IAM com permissão para acessar o banco de dados. Anexar esta função do IAM à instância do EC2",
      "Anexar um volume adicional à instância do EC2 com criptografia habilitada. Mover o arquivo de configuração para o volume criptografado",
      "Instalar um certificado raiz confiável da Amazon na instância do aplicativo e usar conexões criptografadas SSL/TLS com o banco de dados",
      "Mover o arquivo de configuração para um bucket do Amazon S3. Criar uma função do IAM com permissão para o bucket e anexá-lo à instância do EC2"
    ],
    "correct": 0
  },
  {
    "question": "Um aplicativo executado no Amazon EC2 precisa invocar de forma assíncrona uma função do AWS Lambda para realizar o processamento de dados. Os serviços devem ser dissociados. Qual serviço pode ser usado para desacoplar os serviços de computação?",
    "options": [
      "AWS Config",
      "Amazon SNS",
      "AWS Step Functions",
      "Amazon MQ"
    ],
    "correct": 1
  },
  {
    "question": "As instâncias do Amazon EC2 em um ambiente de desenvolvimento são executadas entre 9h e 17h de segunda a sexta-feira. As instâncias de produção são executadas 24 horas por dia, 7 dias por semana. Quais modelos de precificação devem ser usados?",
    "options": [
      "Usar instâncias sob demanda para o ambiente de produção",
      "Usar instâncias reservadas para o ambiente de produção",
      "Reservas de capacidade sob demanda para o ambiente de desenvolvimento",
      "Usar instâncias reservadas para o ambiente de desenvolvimento"
    ],
    "correct": 1
  },
  {
    "question": "Uma Amazon VPC contém várias instâncias do Amazon EC2. As instâncias precisam fazer chamadas de API para o Amazon DynamoDB. Um arquiteto de soluções precisa garantir que as chamadas de API não atravessem a Internet. Como pode ser isto alcançado?",
    "options": [
      "Criar um gateway endpoint para o DynamoDB",
      "Criar uma nova tabela do DynamoDB que usa o endpoint",
      "Criar um ENI para o endpoint em cada uma das sub-redes da VPC",
      "Criar uma entrada na tabela de rotas para o endpoint"
    ],
    "correct": 0
  },
  {
    "question": "Um arquiteto de soluções foi encarregado de reimplantar um aplicativo em execução na AWS para permitir alta disponibilidade. O aplicativo processa as mensagens recebidas em uma fila do ActiveMQ em execução em uma única instância do Amazon EC2. As mensagens são então processadas por um aplicativo consumidor em execução no Amazon EC2. Depois de processar as mensagens, o aplicativo consumidor grava os resultados em um banco de dados MySQL em execução no Amazon EC2. Qual arquitetura oferece a maior disponibilidade e baixa complexidade operacional?",
    "options": [
      "Implantar um segundo servidor Active MQ em outra zona de disponibilidade. Iniciar uma instância EC2 de consumidor adicional em outra zona de disponibilidade. Usar replicação de banco de dados MySQL para outra zona de disponibilidade",
      "Implante o Amazon MQ com agentes ativos/em espera configurados em duas zonas de disponibilidade. Crie um grupo de Auto Scaling para as instâncias do EC2 de consumidor em duas zonas de disponibilidade. Use um banco de dados MySQL do Amazon RDS com Multi-AZ habilitado",
      "Implantar Amazon MQ com agentes ativos/em espera configurados em duas zonas de disponibilidade. Executar uma instância EC2 de consumidor adicional em outra zona de disponibilidade. Usar Amazon RDS para MySQL com Multi-AZ habilitado",
      "Implantar Amazon MQ com agentes ativos/em espera configurados em duas zonas de disponibilidade. Executar uma instância EC2 de consumidor adicional em outra zona de disponibilidade. Usar replicação de banco de dados MySQL para outra zona de disponibilidade"
    ],
    "correct": 1
  },
  {
    "question": "Uma empresa hospeda um jogo multiplayer na AWS. O aplicativo usa instâncias do Amazon EC2 em uma única zona de disponibilidade e os usuários se conectam pela camada 4. O arquiteto de soluções foi encarregado de tornar a arquitetura altamente disponível e também mais econômica. Como o arquiteto de soluções pode atender melhor a esses requisitos?",
    "options": [
      "Configurar um grupo de Auto Scaling para adicionar ou remover instâncias em várias zonas de disponibilidade automaticamente",
      "Configurar um Application Load Balancer na frente das instâncias do EC2",
      "Aumentar o número de instâncias e usar tipos de instância EC2 menores",
      "Configurar um Network Load Balancer na frente das instâncias do EC2"
    ],
    "correct": 0
  },
  {
    "question": "Uma empresa usa uma instância de banco de dados MySQL do Amazon RDS para armazenar dados de pedidos de clientes. A equipe de segurança solicitou que a criptografia SSL/TLS em trânsito seja usada para criptografar conexões com o banco de dados de servidores de aplicativos. Os dados no banco de dados estão atualmente criptografados em repouso usando uma chave do AWS KMS. Como um Arquiteto de Soluções pode habilitar a criptografia em trânsito?",
    "options": [
      "Faça download dos certificados raiz fornecidos pela AWS. Use os certificados ao se conectar à instância de banco de dados do RDS",
      "Fazer um snapshot da instância do RDS. Restaurar o snapshot para uma nova instância com criptografia em trânsito habilitada",
      "Adicionar um certificado auto-assinado à instância de banco de dados do RDS. Usar os certificados em todas as conexões com a instância de banco de dados do RDS",
      "Ative a criptografia em trânsito usando o console de gerenciamento do RDS e obtenha uma chave usando o AWS KMS"
    ],
    "correct": 0
  },
  {
    "question": "Uma organização deseja compartilhar atualizações regulares sobre seu trabalho beneficente usando páginas da Web estáticas. Espera-se que as páginas gerem uma grande quantidade de visualizações de todo o mundo. Os arquivos são armazenados em um bucket do Amazon S3. Um arquiteto de soluções foi solicitado a projetar uma solução eficiente e eficaz. Qual ação o arquiteto de soluções deve tomar para conseguir isso?",
    "options": [
      "Gerar URLs pré-assinados para os arquivos",
      "Usar o Amazon CloudFront com o bucket do S3 como origem",
      "Usar o recurso de geoproximidade do Amazon Route 53",
      "Usar replicação entre regiões para todas as regiões"
    ],
    "correct": 1
  },
  {
    "question": "Um novo aplicativo deve ser publicado em várias regiões do mundo. O arquiteto precisa garantir que apenas 2 endereços IP sejam incluídos na lista de permissões. A solução deve rotear o tráfego de forma inteligente para menor latência e fornecer failover regional rápido. Como isso pode ser alcançado?",
    "options": [
      "Iniciar instâncias do EC2 em várias regiões atrás de um ALB e usar o Amazon CloudFront com um par de endereços IP estáticos",
      "Iniciar instâncias do EC2 em várias regiões atrás de um NLB com um endereço IP estático",
      "Iniciar instâncias do EC2 em várias regiões atrás de um NLB e usar o AWS Global Accelerator",
      "Iniciar instâncias do EC2 em várias regiões atrás de um ALB e usar uma política de roteamento de failover do Route 53"
    ],
    "correct": 2
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