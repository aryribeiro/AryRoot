# app.py - FIXED VERSION
import streamlit as st
from core import setup_data_directory, db_circuit_breaker
from professor import render_teacher_login, render_teacher_dashboard, render_teacher_game_control, render_teacher_signup, render_upload_questions_json_page 
from aluno import render_student_home, render_waiting_room, render_game, render_game_results
from dotenv import load_dotenv
import time
import threading
from datetime import datetime
import random
import logging
from typing import Dict, Any

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

# Configurações da página
st.set_page_config(
    page_title="AryRoot | Quiz Game Multiplayer",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="auto"
)

# ==================== ADVANCED HEALTH CHECK ====================
class AdvancedHealthCheck:
    """Health check com métricas detalhadas - FIXED: integração com circuit breaker"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._last_check = datetime.now()
        self._system_status = "healthy"
        self.metrics = {
            'db_latency_ms': [],
            'cache_hit_rate': 0.0,
            'active_connections': 0,
            'circuit_breaker_state': 'CLOSED',
            'total_requests': 0,
            'failed_requests': 0
        }
        self._max_latency_samples = 100
    
    def get_status(self) -> str:
        """Retorna status do sistema"""
        with self._lock:
            now = datetime.now()
            if (now - self._last_check).total_seconds() > 60:
                self._check_system_health()
                self._last_check = now
            return self._system_status
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Status detalhado para debugging"""
        with self._lock:
            avg_latency = sum(self.metrics['db_latency_ms']) / len(self.metrics['db_latency_ms']) if self.metrics['db_latency_ms'] else 0
            error_rate = (self.metrics['failed_requests'] / self.metrics['total_requests'] * 100) if self.metrics['total_requests'] > 0 else 0
            
            return {
                'status': self._system_status,
                'metrics': {
                    'avg_db_latency_ms': round(avg_latency, 2),
                    'cache_hit_rate': self.metrics['cache_hit_rate'],
                    'circuit_breaker_state': self.metrics['circuit_breaker_state'],
                    'error_rate_percent': round(error_rate, 2),
                    'total_requests': self.metrics['total_requests']
                },
                'timestamp': datetime.now().isoformat()
            }
    
    def _check_system_health(self):
        """Verifica saúde do sistema"""
        try:
            from core import get_db_connection
            
            start_time = time.time()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            # Registrar latência
            latency_ms = (time.time() - start_time) * 1000
            self._record_latency(latency_ms)
            
            # Atualizar estado do circuit breaker
            self.metrics['circuit_breaker_state'] = db_circuit_breaker.state.value
            
            # Determinar status baseado em métricas
            if db_circuit_breaker.state.value == 'OPEN':
                self._system_status = "degraded"
            elif latency_ms > 200:  # Latência alta
                self._system_status = "degraded"
            else:
                self._system_status = "healthy"
                
            logger.info(f"Health check: {self._system_status} (latency: {latency_ms:.2f}ms)")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self._system_status = "unhealthy"
            self.metrics['circuit_breaker_state'] = 'OPEN'
    
    def _record_latency(self, latency_ms: float):
        """Registra amostra de latência"""
        with self._lock:
            self.metrics['db_latency_ms'].append(latency_ms)
            # Manter apenas últimas N amostras
            if len(self.metrics['db_latency_ms']) > self._max_latency_samples:
                self.metrics['db_latency_ms'].pop(0)
    
    def record_request(self, success: bool = True):
        """Registra requisição para métricas"""
        with self._lock:
            self.metrics['total_requests'] += 1
            if not success:
                self.metrics['failed_requests'] += 1

# Instância global do health check
health_check = AdvancedHealthCheck()

# ==================== CSS GLOBAL (constante, injetado uma vez por rerun) ====================
_GLOBAL_CSS = """<style>
    .main { background: linear-gradient(to bottom, #e0f7fa, #ffffff); padding: 20px; }
    button[data-testid="stBaseButton-primary"], button[kind="primary"] { background-color: #4CAF50 !important; color: white !important; font-weight: bold; border-radius: 12px; padding: 12px 24px; border: none !important; box-shadow: 0 4px 8px rgba(0,0,0,0.1); transition: all 0.3s ease; cursor: pointer; }
    button[data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover { background-color: #45a049 !important; box-shadow: 0 6px 12px rgba(0,0,0,0.15); transform: translateY(-2px); }
    .stButton > button:disabled { background-color: #cccccc !important; cursor: not-allowed; transform: none; }
    button[data-testid="stBaseButton-secondary"], button[kind="secondary"] { background-color: white !important; color: #333 !important; border: 1px solid #ddd !important; border-radius: 10px; padding: 8px 16px; transition: all 0.2s ease; }
    button[data-testid="stBaseButton-secondary"]:hover, button[kind="secondary"]:hover { background-color: #f5f5f5 !important; }
    .title { color: #2E7D32; text-align: center; font-size: 3.5rem; margin-bottom: 2rem; font-weight: bold; text-shadow: 1px 1px 2px rgba(0,0,0,0.1); }
    .connection-status { position: fixed; top: 10px; right: 10px; z-index: 9999; padding: 5px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; color: white; }
    .status-healthy { background-color: #4CAF50; }
    .status-degraded { background-color: #FF9800; }
    .status-unhealthy { background-color: #F44336; }
    .question-number { text-align: center; font-size: 1.1rem; margin-bottom: 0.5rem; color: #555; }
    .question-text { font-size: 1.15rem; text-align: center; margin-bottom: 1rem; font-weight: bold; line-height: 1.4; }
    .result-correct { color: #2E7D32; font-size: 1.5rem; text-align: center; margin-top: 1rem; animation: bounce 0.6s ease-in-out; }
    .result-incorrect { color: #C62828; font-size: 1.5rem; text-align: center; margin-top: 1rem; animation: shake 0.6s ease-in-out; }
    .countdown { font-size: 4rem; text-align: center; color: #2E7D32; font-weight: bold; animation: pulse 1s ease-in-out infinite; }
    .custom-ranking-table-container { display: flex; justify-content: center; margin-top: 20px; margin-bottom: 30px; }
    .custom-ranking-table { width: 100%; max-width: 650px; border-collapse: collapse; background-color: #ffffff; box-shadow: 0 4px 8px rgba(0,0,0,0.15); border-radius: 10px; overflow: hidden; }
    .custom-ranking-table th, .custom-ranking-table td { border: none; border-bottom: 1px solid #e8e8e8; padding: 12px 15px; text-align: center; font-size: 0.95rem; vertical-align: middle; }
    .custom-ranking-table tr:last-child td { border-bottom: none; }
    .custom-ranking-table th { background-color: #2E7D32; color: white; font-weight: 600; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .custom-ranking-table tr:nth-child(even) { background-color: #f9f9f9; }
    .custom-ranking-table tr.current-player-row td { background-color: #e0f7fa !important; font-weight: bold; }
    .stApp .block-container { margin-left: auto; margin-right: auto; max-width: 900px; }
    @keyframes bounce { 0%, 20%, 60%, 100% { transform: translateY(0); } 40% { transform: translateY(-20px); } 80% { transform: translateY(-10px); } }
    @keyframes shake { 0%, 100% { transform: translateX(0); } 10%, 30%, 50%, 70%, 90% { transform: translateX(-10px); } 20%, 40%, 60%, 80% { transform: translateX(10px); } }
    @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }
    .loading-spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 2s linear infinite; margin: 20px auto; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    header { display: none !important; }
    footer { display: none !important; }
    #MainMenu { display: none !important; }
    .reportview-container .main .block-container, .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; margin-bottom: 0rem !important; }
</style>"""

st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

# ==================== INICIALIZAÇÃO ====================
_db_initialized = False

def initialize_database_with_retry(max_retries: int = 3) -> bool:
    """Inicializar banco com retry e backoff — runs once per process."""
    global _db_initialized
    if _db_initialized:
        return True

    for attempt in range(max_retries):
        try:
            setup_data_directory()
            _db_initialized = True
            logger.info("Database initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Database init failed (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                delay = 1 * (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(delay)
                continue
            else:
                logger.critical("Failed to initialize database after all retries")
                return False

    return False

def init_session_state():
    """Inicializar estado de sessão com validação - FIXED"""
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

def show_system_status():
    """Mostra status do sistema no canto superior direito"""
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

# ==================== SESSION VALIDATION ====================
def validate_session_timeout():
    """Valida timeout de sessão - FIXED: com unified check"""
    current_time = time.time()
    last_activity = st.session_state.get('last_activity', current_time)
    timeout = 7200  # 2 horas
    
    if current_time - last_activity > timeout:
        logger.info("Session expired due to inactivity")
        # Limpar sessão expirada
        keys_to_clear = [key for key in st.session_state.keys() 
                        if key not in ['session_initialized']]
        for key in keys_to_clear:
            del st.session_state[key]
        
        st.session_state.page = "home"
        st.warning("Sessão expirada. Faça login novamente.")
        return False
    
    return True

def validate_page_access(page: str) -> bool:
    """Valida acesso à página baseado em autenticação"""
    protected_pages = {
        "waiting_room": ["student"],
        "game": ["student"],
        "teacher_dashboard": ["teacher"],
        "teacher_game_control": ["teacher"],
        "teacher_signup": ["teacher"],  # Admin pode acessar
        "teacher_upload_json": ["teacher"],
        "game_results": ["student", "teacher"]
    }
    
    if page not in protected_pages:
        return True
    
    user_type = st.session_state.get("user_type")
    username = st.session_state.get("username")
    
    # Permitir acesso se tipo de usuário correto
    if user_type in protected_pages[page]:
        return True
    
    # Admin tem acesso especial
    if username == "professor" and user_type == "teacher":
        return True
    
    return False

# ==================== PÁGINAS ====================
def render_home():
    """Página inicial otimizada"""
    st.session_state.last_activity = time.time()
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

# ==================== MAIN ====================
def main():
    """Função principal com error handling robusto - FIXED"""
    try:
        # Inicializar banco de dados
        if not initialize_database_with_retry():
            st.error("Sistema temporariamente indisponível. Tente novamente em alguns minutos.")
            st.markdown(
                "<div style='text-align: center; margin-top: 50px;'>"
                "<div class='loading-spinner'></div>"
                "<p>Tentando reconectar...</p></div>",
                unsafe_allow_html=True
            )
            st.stop()
            return
        
        # Inicializar estado da sessão
        init_session_state()
        
        # Validar timeout de sessão
        if not validate_session_timeout():
            st.rerun()
            return
        
        # Registrar requisição no health check
        health_check.record_request(success=True)
        
        # Roteamento de páginas
        page = st.session_state.get("page", "home")
        
        # Validar acesso à página
        if not validate_page_access(page):
            logger.warning(f"Unauthorized access attempt to page: {page}")
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
                logger.warning(f"Unknown page requested: {page}")
                st.session_state.page = "home"
                st.rerun()
        
        except Exception as page_error:
            logger.error(f"Page rendering error: {page_error}", exc_info=True)
            st.error("Erro temporário na página. Recarregando...")

            st.session_state.connection_issues = st.session_state.get("connection_issues", 0) + 1
            health_check.record_request(success=False)

            if st.session_state.connection_issues > 3:
                logger.warning("Too many connection issues, redirecting to home")
                st.session_state.page = "home"
                st.session_state.connection_issues = 0
                st.error("Muitos problemas de conexão. Retornando ao início.")

            time.sleep(1)
            st.rerun()
    
    except Exception as main_error:
        logger.critical(f"Critical application error: {main_error}", exc_info=True)
        health_check.record_request(success=False)
        st.error("Sistema temporariamente indisponível. Atualize a página manualmente.")
        st.stop()

if __name__ == "__main__":
    main()

# Rodapé com informações de contato
st.markdown("""
<hr>
<div style="text-align: center;">
    💬 Por <strong>Ary Ribeiro</strong>. Contato via email: <a href="mailto:aryribeiro@gmail.com">aryribeiro@gmail.com</a><br><br>
</div>
""", unsafe_allow_html=True)