# app.py
import streamlit as st
from core import setup_data_directory
from professor import render_teacher_login, render_teacher_dashboard, render_teacher_game_control, render_teacher_signup, render_upload_questions_json_page 
from aluno import render_student_home, render_waiting_room, render_game, render_game_results
from dotenv import load_dotenv
import time
import threading
from datetime import datetime

# Carregar variáveis de ambiente
load_dotenv()

# Configurações da página
st.set_page_config(
    page_title="AryRoot | Quiz Game Multiplayer",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Sistema de Health Check
class HealthCheck:
    def __init__(self):
        self._lock = threading.RLock()
        self._last_check = datetime.now()
        self._system_status = "healthy"
    
    def get_status(self):
        with self._lock:
            # Verificar status do sistema a cada 60 segundos
            now = datetime.now()
            if (now - self._last_check).total_seconds() > 60:
                self._check_system_health()
                self._last_check = now
            return self._system_status
    
    def _check_system_health(self):
        try:
            # Teste básico de conectividade com o banco
            from core import get_db_connection
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
            self._system_status = "healthy"
        except Exception:
            self._system_status = "degraded"

# Instância global do health check
health_check = HealthCheck()

# CSS otimizado com melhor performance
st.markdown("""
<style>
    .main {
        background: linear-gradient(to bottom, #e0f7fa, #ffffff);
        padding: 20px;
    }
    .stButton > button {
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        border-radius: 12px;
        padding: 12px 24px;
        border: none;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        cursor: pointer;
    }
    .stButton > button:hover {
        background-color: #45a049;
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        transform: translateY(-2px);
    }
    .stButton > button:disabled {
        background-color: #cccccc;
        cursor: not-allowed;
        transform: none;
    }
    .title {
        color: #2E7D32;
        text-align: center;
        font-size: 3.5rem;
        margin-bottom: 2rem;
        font-weight: bold;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
    }
    .connection-status {
        position: fixed;
        top: 10px;
        right: 10px;
        z-index: 9999;
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 12px;
        font-weight: bold;
        color: white;
    }
    .status-healthy {
        background-color: #4CAF50;
    }
    .status-degraded {
        background-color: #FF9800;
    }
    .status-error {
        background-color: #F44336;
    }
    .question-number {
        text-align: center;
        font-size: 1.5rem;
        margin-bottom: 1rem;
        color: #555;
    }
    .question-text {
        font-size: 2rem;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: bold;
        line-height: 1.3;
    }
    .result-correct {
        color: #2E7D32;
        font-size: 2rem;
        text-align: center;
        margin-top: 1rem;
        animation: bounce 0.6s ease-in-out;
    }
    .result-incorrect {
        color: #C62828;
        font-size: 2rem;
        text-align: center;
        margin-top: 1rem;
        animation: shake 0.6s ease-in-out;
    }
    .countdown {
        font-size: 4rem;
        text-align: center;
        color: #2E7D32;
        font-weight: bold;
        animation: pulse 1s ease-in-out infinite;
    }
    .custom-ranking-table-container {
        display: flex;
        justify-content: center;
        margin-top: 20px;
        margin-bottom: 30px;
    }
    .custom-ranking-table {
        width: 100%;
        max-width: 650px;
        border-collapse: collapse;
        background-color: #ffffff;
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        border-radius: 10px;
        overflow: hidden;
    }
    .custom-ranking-table th, .custom-ranking-table td {
        border: none;
        border-bottom: 1px solid #e8e8e8;
        padding: 12px 15px;
        text-align: center;
        font-size: 0.95rem;
        vertical-align: middle;
    }
    .custom-ranking-table tr:last-child td {
        border-bottom: none;
    }
    .custom-ranking-table th {
        background-color: #2E7D32;
        color: white;
        font-weight: 600;
        font-size: 1rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .custom-ranking-table tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    .custom-ranking-table tr.current-player-row td {
        background-color: #e0f7fa !important;
        font-weight: bold;
    }
    .stApp .block-container {
        margin-left: auto;
        margin-right: auto;
        max-width: 900px;
    }
    @keyframes bounce {
        0%, 20%, 60%, 100% { transform: translateY(0); }
        40% { transform: translateY(-20px); }
        80% { transform: translateY(-10px); }
    }
    @keyframes shake {
        0%, 100% { transform: translateX(0); }
        10%, 30%, 50%, 70%, 90% { transform: translateX(-10px); }
        20%, 40%, 60%, 80% { transform: translateX(10px); }
    }
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
    .loading-spinner {
        border: 4px solid #f3f3f3;
        border-top: 4px solid #3498db;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        animation: spin 2s linear infinite;
        margin: 20px auto;
    }
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    /* Esconder elementos do Streamlit */
    header {display: none !important;}
    footer {display: none !important;}
    #MainMenu {display: none !important;}
    .reportview-container .main .block-container,
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
        margin-bottom: 0rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Inicializar o banco de dados SQLite com retry
def initialize_database():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            setup_data_directory()
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))  # Backoff progressivo
                continue
            else:
                st.error(f"Erro ao inicializar banco de dados: {e}")
                return False

# Função para inicializar sessão com validação
def init_session_state():
    # Inicializar estado base
    defaults = {
        "page": "home",
        "user_type": None,
        "username": None,
        "game_code": None,
        "selected_icon": None,
        "answer_time": None,
        "show_ranking": False,
        "selected_answer": None,
        "temp_questions": [],
        "session_initialized": True,
        "connection_issues": 0,
        "last_activity": time.time()
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

# Monitoramento de atividade
def track_activity():
    st.session_state.last_activity = time.time()

# Função para mostrar status do sistema
def show_system_status():
    status = health_check.get_status()
    status_class = f"connection-status status-{status}"
    
    if status == "healthy":
        status_text = "🟢 Sistema OK"
    elif status == "degraded":
        status_text = "🟡 Performance reduzida"
    else:
        status_text = "🔴 Problemas de conexão"
    
    st.markdown(
        f'<div class="{status_class}">{status_text}</div>',
        unsafe_allow_html=True
    )

# Página Inicial otimizada
def render_home():
    track_activity()
    show_system_status()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            "<p style='text-align: center; font-size: 52px; margin-bottom: 0px;'>"
            "<strong>🎮AryRoot</strong></p>", 
            unsafe_allow_html=True
        )
        st.markdown(
            "<p style='text-align: center; font-size: 24px; margin-bottom: 0px;'>"
            "<strong> Quiz Game Multiplayer</strong></p>", 
            unsafe_allow_html=True
        )
        
        # Tabs com cache de estado
        if 'active_tab' not in st.session_state:
            st.session_state.active_tab = 0
        
        tab1, tab2 = st.tabs(["Estudante", "Professor"])
        
        with tab1:
            render_student_home()
        with tab2:
            render_teacher_login()

# Função principal com error handling
def main():
    try:
        # Inicializar banco de dados
        if not initialize_database():
            st.error("Sistema temporariamente indisponível. Tente novamente em alguns minutos.")
            return
        
        # Inicializar estado da sessão
        init_session_state()
        
        # Verificar timeout de sessão (30 minutos)
        current_time = time.time()
        if current_time - st.session_state.last_activity > 1800:  # 30 minutos
            # Limpar sessão expirada
            for key in list(st.session_state.keys()):
                if key not in ['session_initialized']:
                    del st.session_state[key]
            st.session_state.page = "home"
            st.warning("Sessão expirada. Faça login novamente.")
        
        # Roteamento de páginas
        page = st.session_state.get("page", "home")
        
        # Verificar se a página requer autenticação
        protected_pages = ["waiting_room", "game", "teacher_dashboard", "teacher_game_control"]
        if page in protected_pages:
            if not st.session_state.get("username") or not st.session_state.get("user_type"):
                st.warning("Acesso não autorizado. Redirecionando...")
                st.session_state.page = "home"
                st.rerun()
                return
        
        # Renderizar página com tratamento de erro
        try:
            if page == "home":
                render_home()
            elif page == "waiting_room":
                render_waiting_room()
            elif page == "teacher_dashboard":
                render_teacher_dashboard()
            elif page == "teacher_game_control":
                render_teacher_game_control()
            elif page == "game":
                render_game()
            elif page == "game_results":
                render_game_results()
            elif page == "teacher_signup":
                render_teacher_signup()
            elif page == "teacher_upload_json": 
                render_upload_questions_json_page()
            else: 
                # Fallback para página desconhecida
                st.warning("Página não encontrada. Redirecionando para home...")
                st.session_state.page = "home"
                time.sleep(1)
                st.rerun()
        
        except Exception as page_error:
            st.error("Erro temporário na página. Recarregando...")
            
            # Incrementar contador de problemas de conexão
            st.session_state.connection_issues = st.session_state.get("connection_issues", 0) + 1
            
            # Se muitos erros, redirecionar para home
            if st.session_state.connection_issues > 3:
                st.session_state.page = "home"
                st.session_state.connection_issues = 0
                st.error("Muitos problemas de conexão. Retornando ao início.")
            
            # Aguardar antes de tentar novamente
            time.sleep(2)
            st.rerun()
    
    except Exception as main_error:
        st.error("Sistema temporariamente indisponível. Atualizando página...")
        # Log do erro para depuração
        print(f"Erro principal da aplicação: {main_error}")
        time.sleep(3)
        st.rerun()

# Wrapper para execução resiliente
def resilient_main():
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            main()
            break  # Sucesso, sair do loop
        except Exception as e:
            if attempt < max_attempts - 1:
                st.error(f"Problema temporário (tentativa {attempt + 1}/{max_attempts}). Recarregando...")
                time.sleep(2 * (attempt + 1))  # Backoff exponencial
                st.rerun()
            else:
                st.error("Sistema temporariamente indisponível. Tente atualizar a página.")
                st.markdown(
                    "<div style='text-align: center; margin-top: 50px;'>"
                    "<div class='loading-spinner'></div>"
                    "<p>Tentando reconectar...</p></div>",
                    unsafe_allow_html=True
                )

if __name__ == "__main__":
    resilient_main()

# Rodapé com informações de contato
st.markdown("""
<hr>
<div style="text-align: center;">
    💬 Por <strong>Ary Ribeiro</strong>. Contato via email: <a href="mailto:aryribeiro@gmail.com">aryribeiro@gmail.com</a><br><br>
</div>
""", unsafe_allow_html=True)