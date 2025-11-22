# aluno.py - FIXED VERSION
import streamlit as st
import time
from core import Game, PLAYER_ICONS, game_cache
from streamlit.components.v1 import html
import os
import uuid
from datetime import datetime
import threading
import logging

logger = logging.getLogger(__name__)

# ==================== UNIFIED SESSION MANAGER ====================
class UnifiedSessionManager:
    """Gerenciador único de sessão - FIXED: sincroniza com st.session_state"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self.timeout = 1800  # 30 minutos
    
    def get_session_id(self):
        """Retorna session_id único"""
        with self._lock:
            if 'session_id' not in st.session_state:
                st.session_state.session_id = str(uuid.uuid4())
            return st.session_state.session_id
    
    def update_activity(self):
        """Atualiza timestamp de atividade"""
        with self._lock:
            st.session_state.last_activity = time.time()
    
    def is_session_valid(self) -> bool:
        """Valida se sessão ainda é válida"""
        with self._lock:
            last_activity = st.session_state.get('last_activity', 0)
            return (time.time() - last_activity) < self.timeout
    
    def validate_and_refresh(self) -> bool:
        """Valida sessão e atualiza timestamp atomicamente - NEW"""
        with self._lock:
            if not self.is_session_valid():
                self.clear()
                return False
            self.update_activity()
            return True
    
    def clear(self):
        """Limpa dados da sessão"""
        with self._lock:
            keys_to_clear = [
                'session_id', 'username', 'game_code', 'user_type',
                'selected_icon', 'answer_time', 'show_ranking',
                'last_activity', 'input_game_code', 'input_nickname'
            ]
            for key in keys_to_clear:
                if key in st.session_state:
                    del st.session_state[key]

# Instância global do session manager
session_manager = UnifiedSessionManager()

# ==================== DEBOUNCED BUTTON ====================
class DebouncedButton:
    """Previne double-clicks com cooldown - NEW"""
    
    def __init__(self, cooldown: float = 1.5):
        self.last_click = {}
        self.cooldown = cooldown
        self._lock = threading.RLock()
    
    def is_allowed(self, button_id: str) -> bool:
        """Verifica se botão pode ser clicado"""
        with self._lock:
            now = time.time()
            last = self.last_click.get(button_id, 0)
            
            if now - last >= self.cooldown:
                self.last_click[button_id] = now
                return True
            
            logger.warning(f"Debounced button click: {button_id}")
            return False
    
    def reset(self, button_id: str):
        """Reset cooldown para botão específico"""
        with self._lock:
            self.last_click.pop(button_id, None)

# Instância global de debouncer
button_debouncer = DebouncedButton(cooldown=1.5)

def navigate_to(page):
    """Navega para página com tracking de atividade"""
    with st.sidebar:
        st.session_state.page = page
    session_manager.update_activity()

# ==================== RESILIENT OPERATIONS ====================
def resilient_game_operation(func, max_retries=3):
    """Wrapper para operações de jogo com retry - FIXED: melhor error handling"""
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            session_manager.update_activity()
            result = func()
            
            # Se resultado é None, considerar como falha soft
            if result is None and attempt < max_retries - 1:
                logger.warning(f"Operation returned None, retry {attempt+1}/{max_retries}")
                time.sleep(0.5 * (2 ** attempt))
                
                # Limpar cache para forçar reload
                if 'game_code' in st.session_state:
                    game_cache.delete(f"game:{st.session_state.game_code}")
                continue
            
            return result
            
        except Exception as e:
            last_exception = e
            logger.error(f"Game operation error (attempt {attempt+1}): {e}")
            
            if attempt < max_retries - 1:
                delay = 0.5 * (2 ** attempt)
                time.sleep(delay)
                
                # Limpar cache em erro
                if 'game_code' in st.session_state:
                    game_cache.delete(f"game:{st.session_state.game_code}")
            continue
    
    # Todas tentativas falharam
    if last_exception:
        st.error(f"Erro de conexão. Por favor, tente novamente.")
    return None

# Script JavaScript otimizado
silent_audio_script = """
<script>
(function() {
    let activated = false;
    function activateAudio() {
        if (activated) return;
        activated = true;
        try {
            var audio = new Audio('/static/silent.mp3');
            audio.play().catch(() => {});
        } catch(e) {}
    }
    
    ['click', 'touchstart', 'keydown'].forEach(event => {
        document.addEventListener(event, activateAudio, { once: true, passive: true });
    });
    
    setTimeout(activateAudio, 1000);
})();
</script>
"""

def get_current_game():
    """Obtém jogo atual com validação de sessão - FIXED: melhor error handling"""
    current_game_code = st.session_state.get("game_code")
    if not current_game_code:
        return None
    
    def load_game():
        return Game.get_by_code(current_game_code)
    
    return resilient_game_operation(load_game)

def validate_session():
    """Valida sessão do usuário - FIXED: usa método unificado"""
    if not session_manager.validate_and_refresh():
        # Sessão expirada
        navigate_to("home")
        st.error("Sessão expirada. Faça login novamente.")
        st.rerun()
        return False
    return True

def render_student_home():
    html(silent_audio_script, height=0)
    st.markdown("<p style='text-align: center; font-size: 24px; margin-bottom: 0px;'>🚀Entrar no Jogo</p>", unsafe_allow_html=True)
    
    # Estado persistente dos inputs
    if 'input_game_code' not in st.session_state:
        st.session_state.input_game_code = ""
    if 'input_nickname' not in st.session_state:
        st.session_state.input_nickname = ""
    
    game_code = st.text_input(
        "Código do jogo", 
        key="join_game_code",
        help="Digite o código fornecido pelo seu professor",
        placeholder="CÓDIGO DO JOGO",
        max_chars=6,
        value=st.session_state.input_game_code
    )
    
    nickname = st.text_input(
        "Seu apelido", 
        key="join_nickname",
        help="Como você quer ser chamado no jogo",
        placeholder="SEU APELIDO",
        max_chars=12,
        value=st.session_state.input_nickname
    )
    
    # Salvar nos estados persistentes
    st.session_state.input_game_code = game_code
    st.session_state.input_nickname = nickname
    
    st.markdown("<p style='text-align: center; font-size: 24px; margin-bottom: 0px;'>🔎Escolha o Emoji</p>", unsafe_allow_html=True)
    icon_cols = st.columns(5)
    for i, icon in enumerate(PLAYER_ICONS):
        with icon_cols[i % 5]:
            if st.button(icon, key=f"icon_{i}", help="Clique para selecionar este"):
                st.session_state.selected_icon = icon
    
    selected_icon_value = st.session_state.get("selected_icon", None)
    st.markdown(f"<p style='text-align:center; padding-top:1px;'>Escolhido: {selected_icon_value if selected_icon_value else 'Nenhum'}</p>", unsafe_allow_html=True)
    
    # Validação e entrada no jogo
    can_join = bool(game_code and nickname and selected_icon_value)
    
    # Debounce no botão de entrada - NEW
    button_id = "join_game_btn"
    
    if st.button("Entrar", disabled=not can_join, key=button_id):
        if not button_debouncer.is_allowed(button_id):
            st.warning("Por favor, aguarde antes de tentar novamente.")
            return
        
        if not can_join:
            st.error("Preencha todos os campos antes de entrar.")
            return
        
        with st.spinner("Conectando ao jogo..."):
            def join_operation():
                return Game.get_by_code(game_code.upper())
            
            current_game = resilient_game_operation(join_operation)
            
            if not current_game:
                st.error("Código de jogo inválido ou servidor temporariamente indisponível. Tente novamente.")
                button_debouncer.reset(button_id)
                return
                
            if current_game.status == "waiting":
                try:
                    added_successfully = current_game.add_player(nickname, selected_icon_value)
                    
                    if added_successfully:
                        # Configurar estado da sessão
                        st.session_state.username = nickname
                        st.session_state.game_code = game_code.upper()
                        st.session_state.user_type = "student"
                        session_manager.get_session_id()
                        session_manager.update_activity()
                        
                        # Limpar inputs
                        st.session_state.input_game_code = ""
                        st.session_state.input_nickname = ""
                        
                        navigate_to("waiting_room")
                        st.rerun()
                    else:
                        st.error("Este apelido já está sendo usado. Escolha outro.")
                        button_debouncer.reset(button_id)
                        
                except Exception as e:
                    logger.error(f"Error joining game: {e}")
                    st.error("Erro ao entrar no jogo. Tente novamente em alguns segundos.")
                    button_debouncer.reset(button_id)
                    
            elif current_game.status == "active":
                st.error("O jogo já começou e não aceita mais jogadores.")
                button_debouncer.reset(button_id)
            else: 
                st.error("Este jogo já foi finalizado.")
                button_debouncer.reset(button_id)

def render_waiting_room():
    if not validate_session():
        return
    
    current_game = get_current_game()
    if not current_game:
        st.error("Jogo não encontrado!")
        navigate_to("home")
        st.rerun()
        return 

    # Verificar mudança de status
    if current_game.status == "active":
        navigate_to("game")
        st.rerun()
        return 

    if current_game.status == "finished": 
        navigate_to("game_results")
        st.rerun()
        return

    st.markdown("<h1 class='title'>⏳ Sala de Espera</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.header(f"🔒Código: {current_game.code}")
        st.write("🕢 Aguarde o professor iniciar o jogo...")
        
        # Status de conexão
        connection_status = st.empty()
        connection_status.success(f"✅ Conectado - {len(current_game.players)} jogadores online")
        
        st.subheader("Jogadores na sala:")
        players_container = st.container()
        
        with players_container:
            if not current_game.players:
                st.info("Nenhum jogador entrou ainda.")
            else:
                player_cols = st.columns(3)
                players_list = list(current_game.players.items())
                for i, (player_name, player_data) in enumerate(players_list):
                    with player_cols[i % 3]:
                        icon = player_data.get('icon', '❓') if isinstance(player_data, dict) else '❓'
                        st.markdown(
                            f"<div style='text-align:center; padding:10px; margin:5px; "
                            f"background-color:#e0f7fa; border-radius:10px;'>"
                            f"<span style='font-size:2rem;'>{icon}</span><br>{player_name}</div>",
                            unsafe_allow_html=True
                        )

    # Auto-refresh com intervalo maior
    time.sleep(3)
    st.rerun()

def render_game():
    if not validate_session():
        return
    
    current_game = get_current_game()
    if not current_game:
        st.error("Jogo não encontrado!")
        navigate_to("home")
        st.rerun()
        return

    # Verificar mudanças de status
    if current_game.status == "waiting":
        navigate_to("waiting_room")
        st.rerun()
        return
    if current_game.status == "finished":
        navigate_to("game_results")
        st.rerun()
        return

    player_name_session = st.session_state.username
    player_data = current_game.players.get(player_name_session, {}) if isinstance(current_game.players, dict) else {}
    player_answers = player_data.get("answers", []) if isinstance(player_data, dict) else []
    
    # Garantir que player_answers é uma lista
    if not isinstance(player_answers, list):
        player_answers = []

    # Verificar se já respondeu a pergunta atual
    already_answered = any(
        isinstance(answer, dict) and answer.get("question") == current_game.current_question 
        for answer in player_answers
    )

    # Mostrar ranking se solicitado
    if st.session_state.get("show_ranking", False): 
        st.markdown("<h1 class='title'>🏆 Ranking Parcial</h1>", unsafe_allow_html=True)
        
        try:
            ranking = current_game.get_ranking()
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                # Tabela de ranking otimizada
                table_html = "<div class='custom-ranking-table-container'><table class='custom-ranking-table'>"
                table_html += "<thead><tr><th>Pos.</th><th>Jogador</th><th>Pontos</th></tr></thead><tbody>"
                
                for i, player_rank_info in enumerate(ranking[:10]): 
                    icon = player_rank_info.get('icon', '❓')
                    name = player_rank_info.get('name', 'Unknown')
                    score = player_rank_info.get('score', 0)
                    table_html += f"<tr><td>{i+1}</td><td>{icon} {name}</td><td>{score}</td></tr>"
                
                table_html += "</tbody></table></div>"
                st.markdown(table_html, unsafe_allow_html=True)
                
                # Posição do jogador atual
                player_position = next(
                    (i+1 for i, p_rank in enumerate(ranking) if p_rank.get("name") == player_name_session), 
                    None
                )
                if player_position:
                    st.markdown(
                        f"<p style='text-align:center; margin-top:20px;'>Sua posição: {player_position}º lugar</p>", 
                        unsafe_allow_html=True
                    )
                
                # Countdown otimizado
                st.markdown("<div class='countdown'>Próxima pergunta em:</div>", unsafe_allow_html=True)
                countdown_placeholder = st.empty()
                
                for i_countdown in range(5, 0, -1): 
                    countdown_placeholder.markdown(
                        f"<div class='countdown'>{i_countdown}</div>", 
                        unsafe_allow_html=True
                    )
                    time.sleep(1)
                
                st.session_state.show_ranking = False
        except Exception as e:
            logger.error(f"Error loading ranking: {e}")
            st.error("Erro ao carregar ranking. Recarregando...")
            st.session_state.show_ranking = False
        
        st.rerun()
        return 

    # Validar índice da pergunta
    current_q_idx_game = current_game.current_question 
    if not (0 <= current_q_idx_game < len(current_game.questions)):
        st.error("Aguardando próxima pergunta...")
        time.sleep(5)
        st.rerun()
        return

    # Interface da pergunta
    st.markdown("<h1 class='title'>🎮 AryRoot</h1>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='question-number'>Pergunta {current_q_idx_game + 1} de {len(current_game.questions)}</div>", 
        unsafe_allow_html=True
    )
    
    question_text = current_game.questions[current_q_idx_game]['question']
    st.markdown(f"<div class='question-text'>{question_text}</div>", unsafe_allow_html=True)
    
    # Status de conexão
    status_placeholder = st.empty()
    status_placeholder.info("🟢 Conectado")
    
    if not already_answered:
        # Inicializar timer de resposta
        if st.session_state.get("answer_time") is None: 
            st.session_state.answer_time = time.time()

        # Opções de resposta com cores
        option_colors = ["#E57373", "#64B5F6", "#FFD54F", "#81C784"]
        option_text_colors = ["white", "white", "black", "white"]
        option_cols = st.columns(2)

        current_options = current_game.questions[current_q_idx_game]['options']
        
        for i_opt, option in enumerate(current_options):
            button_id = f"option_{i_opt}_{current_q_idx_game}_{player_name_session}"
            
            with option_cols[i_opt % 2]:
                if st.button(
                    option, 
                    key=f"option_{i_opt}_{current_q_idx_game}", 
                    help="Clique para selecionar esta resposta",
                    use_container_width=True,
                    type="primary"
                ):
                    # Debounce check - NOVO
                    if not button_debouncer.is_allowed(button_id):
                        st.warning("Por favor, aguarde antes de responder novamente.")
                        time.sleep(1)
                        st.rerun()
                        return
                    
                    # Processar resposta
                    with st.spinner("Registrando sua resposta..."): 
                        try:
                            time_taken = time.time() - st.session_state.answer_time
                            st.session_state.answer_time = None 
                            
                            # Registrar resposta com retry
                            is_correct, points = current_game.record_answer(
                                player_name_session, i_opt, time_taken
                            )
                            
                            if is_correct is not False:  # Sucesso no registro
                                if is_correct:
                                    st.markdown(
                                        f"<div class='result-correct'>✓ Correto! +{points} pontos</div>", 
                                        unsafe_allow_html=True
                                    )
                                else:
                                    st.markdown(
                                        f"<div class='result-incorrect'>✗ Incorreto</div>", 
                                        unsafe_allow_html=True
                                    )
                                time.sleep(2)
                            else:
                                st.warning("Erro ao registrar resposta. Tente novamente.")
                                button_debouncer.reset(button_id)
                                
                        except Exception as e:
                            logger.error(f"Error recording answer: {e}")
                            st.error("Problema de conexão. Sua resposta pode não ter sido registrada.")
                            button_debouncer.reset(button_id)
                        
                    st.rerun()

        # CSS para as opções
        css_options = ""
        for i_css in range(len(current_options)): 
            css_options += f"""
                button[data-testid='stButton'][key='option_{i_css}_{current_q_idx_game}'] > div > p {{ 
                    color: {option_text_colors[i_css]} !important; 
                }}
                button[data-testid='stButton'][key='option_{i_css}_{current_q_idx_game}'] {{ 
                    background-color: {option_colors[i_css]} !important; 
                    border: none !important; 
                }}
                button[data-testid='stButton'][key='option_{i_css}_{current_q_idx_game}']:hover {{ 
                    background-color: {option_colors[i_css]} !important; 
                    opacity: 0.9 !important; 
                    border: none !important; 
                }}
                button[data-testid='stButton'][key='option_{i_css}_{current_q_idx_game}']:focus {{ 
                    background-color: {option_colors[i_css]} !important; 
                    opacity: 0.9 !important; 
                    border: none !important; 
                    box-shadow: none !important; 
                }}
            """
        st.markdown(f"<style>{css_options}</style>", unsafe_allow_html=True)
    else:
        st.info("✅ Você já respondeu esta pergunta. Aguarde a próxima.")
        time.sleep(3) 
        st.rerun()

def render_game_results():
    if not validate_session():
        return
        
    current_game_code = st.session_state.get("game_code")
    if not current_game_code:
        st.error("Código do jogo não encontrado na sessão.")
        navigate_to("home")
        st.rerun()
        return

    current_game_results = get_current_game()
    if not current_game_results:
        st.error("Jogo não encontrado!")
        navigate_to("home")
        st.rerun()
        return

    st.markdown("<h1 class='title' style='text-align: center; margin-bottom: 20px;'>🏆 Resultados Finais</h1>", unsafe_allow_html=True)
    
    try:
        ranking = current_game_results.get_ranking()
        player_name_for_results = st.session_state.get("username")
        player_position = next(
            (i+1 for i, p_res in enumerate(ranking) if p_res.get("name") == player_name_for_results), 
            None
        )

        # CSS para resultados
        st.markdown("""
        <style> 
        audio { display: none; }
        .podium-container { display: flex; justify-content: center; align-items: flex-end; gap: 10px; margin-bottom: 40px; margin-top: 20px; height: 280px; width: 100%; }
        .podium-place { text-align: center; color: white; border-radius: 10px; padding: 15px 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.25); display: flex; flex-direction: column; justify-content: flex-end; align-items: center; position: relative; transition: transform 0.2s ease-in-out; }
        .podium-place:hover { transform: translateY(-5px); }
        .podium-icon { font-size: 3rem; margin-bottom: 8px; line-height: 1; }
        .podium-name { font-size: 1.1rem; font-weight: bold; margin-bottom: 5px; word-break: break-word; }
        .podium-score { font-size: 0.9rem; }
        .first-place { background: linear-gradient(to bottom, #ffd700, #f0c14b); height: 260px; width: 160px; z-index: 3; order: 2; }
        .second-place { background: linear-gradient(to bottom, #c0c0c0, #a8a8a8); height: 220px; width: 140px; z-index: 2; order: 1; }
        .third-place { background: linear-gradient(to bottom, #cd7f32, #b87333); height: 180px; width: 120px; z-index: 1; order: 3; }
        .custom-ranking-table-container { display: flex; justify-content: center; margin-top: 20px; margin-bottom: 30px; }
        .custom-ranking-table { width: 100%; max-width: 650px; border-collapse: collapse; background-color: #ffffff; box-shadow: 0 4px 8px rgba(0,0,0,0.15); border-radius: 10px; overflow: hidden; }
        .custom-ranking-table th, .custom-ranking-table td { border: none; border-bottom: 1px solid #e8e8e8; padding: 12px 15px; text-align: center; font-size: 0.95rem; vertical-align: middle; }
        .custom-ranking-table tr:last-child td { border-bottom: none; }
        .custom-ranking-table th { background-color: #2E7D32; color: white; font-weight: 600; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.5px; }
        .custom-ranking-table tr:nth-child(even) { background-color: #f9f9f9; }
        .custom-ranking-table tr.current-player-row td { background-color: #e0f7fa !important; font-weight: bold; }
        .custom-ranking-table .medal-icon { font-size: 1.2rem; margin-right: 3px; }
        .custom-ranking-table td:nth-child(2) { text-align: left; padding-left: 25px; }
        .custom-ranking-table th:nth-child(1), .custom-ranking-table td:nth-child(1) { width: 15%; } 
        .custom-ranking-table th:nth-child(2), .custom-ranking-table td:nth-child(2) { width: 60%; }
        .custom-ranking-table th:nth-child(3), .custom-ranking-table td:nth-child(3) { width: 25%; }
        </style>
        """, unsafe_allow_html=True)

        # Parabenização para estudantes
        if st.session_state.user_type == "student" and player_position and player_name_for_results:
            st.markdown(
                f"<p style='text-align:center; font-size:1.5rem; color:#2E7D32; margin-bottom: 10px;'>"
                f"Parabéns, {player_name_for_results}! Você ficou em {player_position}º lugar!</p>",
                unsafe_allow_html=True
            )
            
            if "balloons_shown" not in st.session_state: 
                st.session_state.balloons_shown = False
            if not st.session_state.balloons_shown:
                st.balloons()
                st.session_state.balloons_shown = True
            
            # Áudio de comemoração
            audio_path = "static/aplausos.mp3"
            if os.path.exists(audio_path):
                with open(audio_path, "rb") as f: 
                    audio_bytes = f.read()
                st.audio(audio_bytes, format="audio/mp3", autoplay=True)

        # Renderizar pódio
        if len(ranking) > 0:
            podium_html = "<div class='podium-container'>"
            ordered_ranking_podium = [None, None, None]

            if len(ranking) >= 1: 
                ordered_ranking_podium[1] = {'player': ranking[0], 'class': 'first-place'}
            if len(ranking) >= 2: 
                ordered_ranking_podium[0] = {'player': ranking[1], 'class': 'second-place'}
            if len(ranking) >= 3: 
                ordered_ranking_podium[2] = {'player': ranking[2], 'class': 'third-place'}
            
            for podium_entry in ordered_ranking_podium:
                if podium_entry:
                    player_info = podium_entry['player']
                    icon = player_info.get('icon', '❓')
                    name = player_info.get('name', 'Unknown')
                    score = player_info.get('score', 0)
                    podium_html += (
                        f"<div class='podium-place {podium_entry['class']}'>"
                        f"<span class='podium-icon'>{icon}</span>"
                        f"<div class='podium-name'>{name}</div>"
                        f"<div class='podium-score'>{score} pts</div></div>"
                    )
            
            podium_html += "</div>"
            st.markdown(podium_html, unsafe_allow_html=True)
        else:
            st.info("Nenhum jogador participou ou pontuou para exibir o pódio.")

        # Tabela de ranking completo
        st.markdown(
            "<p style='text-align: center; font-size: 24px; margin-top: 30px; margin-bottom: 10px;'>"
            "<strong>📉 Ranking Completo</strong></p>", 
            unsafe_allow_html=True
        )
        
        table_html_ranking = "<div class='custom-ranking-table-container'><table class='custom-ranking-table'>"
        table_html_ranking += "<thead><tr><th>Pos.</th><th>Jogador</th><th>Pontos</th></tr></thead><tbody>"
        
        if not ranking:
            table_html_ranking += "<tr><td colspan='3'>Nenhum jogador participou ou pontuou.</td></tr>"
        else:
            for i_rank_table, player_info_rank in enumerate(ranking): 
                medal = ""
                if i_rank_table == 0: medal = "<span class='medal-icon'>🥇</span>"
                elif i_rank_table == 1: medal = "<span class='medal-icon'>🥈</span>"
                elif i_rank_table == 2: medal = "<span class='medal-icon'>🥉</span>"
                
                is_current_player_student = (
                    player_info_rank.get("name") == player_name_for_results and 
                    st.session_state.user_type == "student"
                )
                row_class = "current-player-row" if is_current_player_student else ""
                
                icon = player_info_rank.get('icon', '❓')
                name = player_info_rank.get('name', 'Unknown')
                score = player_info_rank.get('score', 0)
                
                table_html_ranking += f"<tr class='{row_class}'>"
                table_html_ranking += f"<td>{i_rank_table+1} {medal}</td>"
                table_html_ranking += f"<td>{icon} {name}</td>" 
                table_html_ranking += f"<td>{score}</td></tr>"
        
        table_html_ranking += "</tbody></table></div>"
        st.markdown(table_html_ranking, unsafe_allow_html=True)

    except Exception as e:
        logger.error(f"Error loading results: {e}")
        st.error("Erro ao carregar resultados. Atualizando...")
        time.sleep(2)
        st.rerun()
        return

    # Botões de navegação
    button_col_config = [1.5, 2, 1.5] 
    
    if st.session_state.user_type == "student":
        student_button_cols = st.columns(button_col_config)
        with student_button_cols[1]:
            if st.button("Voltar ao Início", key="back_to_home_results", use_container_width=True):
                # Limpar estados de sessão relacionados ao jogo/aluno
                session_manager.clear()
                navigate_to("home")
                st.rerun()
    
    elif st.session_state.user_type == "teacher":
        teacher_button_cols = st.columns(button_col_config)
        with teacher_button_cols[1]:
            if st.button("Voltar ao Painel do Professor", key="back_to_teacher_dashboard_results", use_container_width=True):
                # Limpar estados específicos do jogo, manter login do professor
                keys_to_clear_teacher_results = ["balloons_shown", "game_code", "show_ranking"]
                for k_clear_teach in keys_to_clear_teacher_results:
                    if k_clear_teach in st.session_state: 
                        del st.session_state[k_clear_teach]
                navigate_to("teacher_dashboard")
                st.rerun()