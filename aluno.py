# aluno.py
import streamlit as st
import time
from core import Game, PLAYER_ICONS 
from streamlit.components.v1 import html
import os

# Função para navegar entre páginas
def navigate_to(page):
    st.session_state.page = page

# Script JavaScript (sem mudanças)
silent_audio_script = """
<script>
document.addEventListener('click', function activateAudio() {
    var audio = new Audio('/static/silent.mp3');
    audio.play().then(() => {
        console.log('Contexto de áudio ativado');
    }).catch(err => {
        console.error('Erro ao ativar áudio:', err);
    });
    document.removeEventListener('click', activateAudio);
}, { once: true });
</script>
"""

def render_student_home():
    html(silent_audio_script, height=0)
    st.markdown("<p style='text-align: center; font-size: 24px; margin-bottom: 0px;'>🚀Entrar no Jogo</p>", unsafe_allow_html=True)
    game_code = st.text_input("Código do jogo", key="join_game_code",
                              help="Digite o código fornecido pelo seu professor",
                              placeholder="CÓDIGO DO JOGO",
                              max_chars=6)
    nickname = st.text_input("Seu apelido", key="join_nickname",
                             help="Como você quer ser chamado no jogo",
                             placeholder="SEU APELIDO",
                             max_chars=12)
    st.markdown("<p style='text-align: center; font-size: 24px; margin-bottom: 0px;'>🔎Escolha o Emoji</p>", unsafe_allow_html=True)
    icon_cols = st.columns(5)
    for i, icon in enumerate(PLAYER_ICONS):
        with icon_cols[i % 5]:
            if st.button(icon, key=f"icon_{i}",
                         help="Clique para selecionar este"):
                st.session_state.selected_icon = icon
    selected_icon_value = st.session_state.get("selected_icon", None)
    st.markdown(f"<p style='text-align:center; padding-top:1px;'>Escolhido: {selected_icon_value if selected_icon_value else 'Nenhum'}</p>", unsafe_allow_html=True)
    
    if st.button("Entrar", disabled=not (game_code and nickname and selected_icon_value)):
        current_game = Game.get_by_code(game_code.upper()) 
        if current_game:
            if current_game.status == "waiting":
                with st.spinner("Entrando no jogo..."): # Adicionado spinner
                    added_successfully = current_game.add_player(nickname, selected_icon_value) 
                
                if added_successfully:
                    st.session_state.username = nickname
                    st.session_state.game_code = game_code.upper()
                    st.session_state.user_type = "student"
                    navigate_to("waiting_room")
                    st.rerun() 
                else:
                    st.error("Este apelido já está sendo usado. Escolha outro.")
            elif current_game.status == "active":
                st.error("O jogo já começou e não aceita mais jogadores.")
            else: 
                st.error("Este jogo já foi finalizado.")
        else:
            st.error("Código de jogo inválido. Verifique e tente novamente.")

def render_waiting_room():
    # Nenhum spinner aqui, pois é uma leitura e loop de espera
    current_game = Game.get_by_code(st.session_state.game_code) 
    if not current_game:
        st.error("Jogo não encontrado!")
        navigate_to("home")
        st.rerun()
        return 

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
        st.header(f"🔑Código: {current_game.code}")
        st.write("🕢 Aguarde o professor iniciar o jogo...")
        st.subheader("Jogadores na sala:")
        if not current_game.players:
            st.info("Nenhum jogador entrou ainda.")
        else:
            player_cols = st.columns(3)
            for i, (player_name, player_data) in enumerate(current_game.players.items()):
                with player_cols[i % 3]:
                    st.markdown(f"<div style='text-align:center; padding:10px; margin:5px; background-color:#e0f7fa; border-radius:10px;'>"
                                f"<span style='font-size:2rem;'>{player_data['icon']}</span><br>{player_name}</div>",
                                unsafe_allow_html=True)
    time.sleep(2)
    st.rerun()

def render_game():
    current_game = Game.get_by_code(st.session_state.game_code) 
    if not current_game:
        st.error("Jogo não encontrado!")
        navigate_to("home")
        st.rerun()
        return

    if current_game.status == "waiting":
        navigate_to("waiting_room")
        st.rerun()
        return
    if current_game.status == "finished":
        navigate_to("game_results")
        st.rerun()
        return

    player_name_session = st.session_state.username
    player_data = current_game.players.get(player_name_session, {}) 
    player_answers = player_data.get("answers", [])
    already_answered = any(answer["question"] == current_game.current_question for answer in player_answers)

    if st.session_state.get("show_ranking", False): 
        st.markdown("<h1 class='title'>🏆 Ranking Parcial</h1>", unsafe_allow_html=True)
        ranking = current_game.get_ranking() 
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            table_html = "<div class='custom-ranking-table-container'><table class='custom-ranking-table'>"
            table_html += "<thead><tr><th>Pos.</th><th>Jogador</th><th>Pontos</th></tr></thead><tbody>"
            for i, player in enumerate(ranking[:10]): 
                table_html += f"<tr><td>{i+1}</td><td>{player['icon']} {player['name']}</td><td>{player['score']}</td></tr>"
            table_html += "</tbody></table></div>"
            st.markdown(table_html, unsafe_allow_html=True)
            player_position = next((i+1 for i, p in enumerate(ranking) if p["name"] == player_name_session), None)
            if player_position:
                st.markdown(f"<p style='text-align:center; margin-top:20px;'>Sua posição: {player_position}º lugar</p>", unsafe_allow_html=True)
            st.markdown("<div class='countdown'>Próxima pergunta em:</div>", unsafe_allow_html=True)
            countdown_placeholder = st.empty() 
            for i_countdown in range(5, 0, -1): # Renomeado i para i_countdown
                countdown_placeholder.markdown(f"<div class='countdown'>{i_countdown}</div>", unsafe_allow_html=True)
                time.sleep(1)
            st.session_state.show_ranking = False
        st.rerun()
        return 

    current_q_idx_game = current_game.current_question 
    st.markdown("<h1 class='title'>🎮 AryRoot</h1>", unsafe_allow_html=True)
    st.markdown(f"<div class='question-number'>Pergunta {current_q_idx_game + 1} de {len(current_game.questions)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='question-text'>{current_game.questions[current_q_idx_game]['question']}</div>", unsafe_allow_html=True)
    
    if not already_answered:
        if st.session_state.get("answer_time") is None: 
            st.session_state.answer_time = time.time()

        option_colors = ["#E57373", "#64B5F6", "#FFD54F", "#81C784"]
        option_text_colors = ["white", "white", "black", "white"]
        option_cols = st.columns(2)

        for i_opt, option in enumerate(current_game.questions[current_q_idx_game]['options']): # Renomeado i para i_opt
            with option_cols[i_opt % 2]:
                if st.button(option, key=f"option_{i_opt}", 
                           help="Clique para selecionar esta resposta",
                           use_container_width=True,
                           type="primary"): 
                    with st.spinner("Registrando sua resposta..."): # Adicionado spinner
                        time_taken = time.time() - st.session_state.answer_time
                        st.session_state.answer_time = None 
                        is_correct, points = current_game.record_answer(player_name_session, i_opt, time_taken) 
                    
                    if is_correct:
                        st.markdown(f"<div class='result-correct'>✓ Correto! +{points} pontos</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='result-incorrect'>✗ Incorreto</div>", unsafe_allow_html=True)
                    time.sleep(1) 
                    st.rerun() 

        num_options = len(current_game.questions[current_q_idx_game]['options'])
        css_options = ""
        for i_css in range(num_options): # Renomeado i para i_css
            css_options += f"button[data-testid='stButton'][key='option_{i_css}'] > div > p {{ color: {option_text_colors[i_css]} !important; }}\n"
            # ... (restante do CSS dinâmico - sem mudança lógica)
            css_options += f"button[data-testid='stButton'][key='option_{i_css}'] {{ background-color: {option_colors[i_css]} !important; border: none !important; }}\n"
            css_options += f"button[data-testid='stButton'][key='option_{i_css}']:hover {{ background-color: {option_colors[i_css]} !important; opacity: 0.9 !important; border: none !important; }}\n"
            css_options += f"button[data-testid='stButton'][key='option_{i_css}']:focus {{ background-color: {option_colors[i_css]} !important; opacity: 0.9 !important; border: none !important; box-shadow: none !important; }}\n"
        st.markdown(f"<style>{css_options}</style>", unsafe_allow_html=True)
    else:
        st.info("Você já respondeu esta pergunta. Aguarde a próxima.")
        time.sleep(2) 
        st.rerun()

# render_game_results (sem mudanças necessárias para o lock, pois é principalmente leitura)
def render_game_results():
    current_game_results = Game.get_by_code(st.session_state.game_code) 
    if not current_game_results:
        st.error("Jogo não encontrado!")
        navigate_to("home")
        st.rerun()
        return

    st.markdown("<h1 class='title' style='text-align: center; margin-bottom: 20px;'>🏆 Resultados Finais</h1>", unsafe_allow_html=True)
    ranking = current_game_results.get_ranking() 
    player_position = next((i+1 for i, p in enumerate(ranking) if p["name"] == st.session_state.username), None)

    # CSS (sem mudanças)
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

    if st.session_state.user_type == "student" and player_position:
        st.markdown(f"<p style='text-align:center; font-size:1.5rem; color:#2E7D32; margin-bottom: 10px;'>"
                    f"Parabéns, {st.session_state.username}! Você ficou em {player_position}º lugar!</p>",
                    unsafe_allow_html=True)
        if "balloons_shown" not in st.session_state: st.session_state.balloons_shown = False
        if not st.session_state.balloons_shown:
            st.balloons(); st.session_state.balloons_shown = True
        audio_path = "static/aplausos.mp3"
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as f: audio_bytes = f.read()
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)
        else:
            st.warning("Arquivo de áudio 'aplausos.mp3' não encontrado.")

    # Pódio e Tabela de Ranking (sem mudanças lógicas)
    if len(ranking) > 0:
        podium_html = "<div class='podium-container'>"
        ordered_ranking_podium = [] 
        if len(ranking) >= 2: ordered_ranking_podium.append({'player': ranking[1], 'class': 'second-place'})
        else: ordered_ranking_podium.append(None) 
        ordered_ranking_podium.append({'player': ranking[0], 'class': 'first-place'})
        if len(ranking) >= 3: ordered_ranking_podium.append({'player': ranking[2], 'class': 'third-place'})
        else: ordered_ranking_podium.append(None) 

        if ordered_ranking_podium[0]:
            podium_html += (f"<div class='podium-place {ordered_ranking_podium[0]['class']}'>"
                            f"<span class='podium-icon'>{ordered_ranking_podium[0]['player']['icon']}</span>"
                            f"<div class='podium-name'>{ordered_ranking_podium[0]['player']['name']}</div>"
                            f"<div class='podium-score'>{ordered_ranking_podium[0]['player']['score']} pts</div></div>")
        podium_html += (f"<div class='podium-place {ordered_ranking_podium[1]['class']}'>"
                        f"<span class='podium-icon'>{ordered_ranking_podium[1]['player']['icon']}</span>"
                        f"<div class='podium-name'>{ordered_ranking_podium[1]['player']['name']}</div>"
                        f"<div class='podium-score'>{ordered_ranking_podium[1]['player']['score']} pts</div></div>")
        if ordered_ranking_podium[2]:
            podium_html += (f"<div class='podium-place {ordered_ranking_podium[2]['class']}'>"
                            f"<span class='podium-icon'>{ordered_ranking_podium[2]['player']['icon']}</span>"
                            f"<div class='podium-name'>{ordered_ranking_podium[2]['player']['name']}</div>"
                            f"<div class='podium-score'>{ordered_ranking_podium[2]['player']['score']} pts</div></div>")
        podium_html += "</div>"
        st.markdown(podium_html, unsafe_allow_html=True)
    else:
        st.info("Nenhum jogador participou ou pontuou para exibir o pódio.")

    st.markdown("<p style='text-align: center; font-size: 24px; margin-top: 30px; margin-bottom: 10px;'><strong>📉 Ranking Completo</strong></p>", unsafe_allow_html=True)
    table_html_ranking = "<div class='custom-ranking-table-container'><table class='custom-ranking-table'>" # Renomeado table_html
    table_html_ranking += "<thead><tr><th>Pos.</th><th>Jogador</th><th>Pontos</th></tr></thead><tbody>"
    if not ranking:
        table_html_ranking += "<tr><td colspan='3'>Nenhum jogador participou ou pontuou.</td></tr>"
    else:
        for i_rank_table, player in enumerate(ranking): # Renomeado i
            medal = ""
            if i_rank_table == 0: medal = "<span class='medal-icon'>🥇</span>"
            elif i_rank_table == 1: medal = "<span class='medal-icon'>🥈</span>"
            elif i_rank_table == 2: medal = "<span class='medal-icon'>🥉</span>"
            is_current_player_student = player["name"] == st.session_state.username and st.session_state.user_type == "student"
            row_class = "current-player-row" if is_current_player_student else ""
            table_html_ranking += f"<tr class='{row_class}'>"
            table_html_ranking += f"<td>{i_rank_table+1} {medal}</td>"
            table_html_ranking += f"<td>{player['icon']} {player['name']}</td>" 
            table_html_ranking += f"<td>{player['score']}</td></tr>"
    table_html_ranking += "</tbody></table></div>"
    st.markdown(table_html_ranking, unsafe_allow_html=True)

    button_col_config = [1.5, 2, 1.5] 
    if st.session_state.user_type == "student":
        student_button_cols = st.columns(button_col_config)
        with student_button_cols[1]:
            if st.button("Voltar ao Início", key="back_to_home_results", use_container_width=True):
                if "balloons_shown" in st.session_state: del st.session_state.balloons_shown
                if "selected_icon" in st.session_state: del st.session_state.selected_icon 
                if "answer_time" in st.session_state: del st.session_state.answer_time
                navigate_to("home")
                st.rerun()
    elif st.session_state.user_type == "teacher":
        teacher_button_cols = st.columns(button_col_config)
        with teacher_button_cols[1]:
            if st.button("Voltar ao Painel do Professor", key="back_to_teacher_dashboard_results", use_container_width=True):
                if "balloons_shown" in st.session_state: del st.session_state.balloons_shown
                navigate_to("teacher_dashboard")
                st.rerun()