# professor.py
import streamlit as st
from core import Teacher, Game, generate_game_code, SAMPLE_QUESTIONS
from core import clear_teacher_from_cache, clear_all_teachers_from_cache, _JSON_WRITE_LOCK_TEACHERS # Adicionado Lock
import bcrypt
import json
import os
import random 
import time
import threading # Para o lock, embora já importado em core

def navigate_to(page):
    st.session_state.page = page

def load_teachers_from_json(): 
    # Leitura não precisa de lock aqui, pois as escritas são serializadas
    teachers_file_path = "data/teachers.json"
    if not os.path.exists(teachers_file_path):
        return {}
    try:
        with open(teachers_file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_all_teachers(teachers_data): 
    # Esta função é chamada pelo admin ao editar/remover professores.
    # Ela já lida com o arquivo inteiro. O lock protegerá esta operação.
    teachers_file_path = "data/teachers.json"
    with _JSON_WRITE_LOCK_TEACHERS: # Protege a escrita do arquivo de professores
        try:
            with open(teachers_file_path, "w", encoding="utf-8") as f:
                json.dump(teachers_data, f, indent=4, ensure_ascii=False)
            clear_all_teachers_from_cache() # Limpa o cache após a modificação em lote
            return True
        except Exception as e:
            st.error(f"Erro ao salvar dados dos professores: {e}")
            return False

# Captcha Logic (sem mudanças)
def generate_captcha():
    num1 = random.randint(1, 10); num2 = random.randint(1, 10)
    operation = random.choice(["+", "-"]);
    if operation == "+": question, answer = f"{num1} + {num2}?", num1 + num2
    else: 
        if num1 < num2: num1, num2 = num2, num1 
        question, answer = f"{num1} - {num2}?", num1 - num2
    st.session_state.captcha_question, st.session_state.captcha_answer = question, answer

def render_teacher_login(): # Sem mudanças diretas de lock aqui
    st.markdown("<p style='text-align: center; font-size: 24px; margin-bottom: 10px;'><strong>🔐 Login do Professor</strong></p>", unsafe_allow_html=True) 
    if "captcha_question" not in st.session_state: generate_captcha()
    _ , central_column, _ = st.columns([0.75, 2.5, 0.75])
    with central_column: 
        login_username = st.text_input("Nome de usuário", key="login_username_captcha_wider")
        login_password = st.text_input("Senha", type="password", key="login_password_captcha_wider")
        st.markdown("<br>", unsafe_allow_html=True) 
        st.markdown(f"**Verificação:** Quanto é **{st.session_state.get('captcha_question', '...')}**?")
        captcha_input_value = st.text_input("Sua resposta para a verificação", key="login_captcha_input_wider", placeholder="Digite o resultado")
        st.markdown("<br>", unsafe_allow_html=True) 
        if st.button("Entrar", key="login_btn_captcha_wider", use_container_width=True):
            # ... (lógica de captcha e login - sem spinner explícito aqui, pois é rápido ou erro)
            current_login_username = st.session_state.login_username_captcha_wider
            current_login_password = st.session_state.login_password_captcha_wider
            current_captcha_input = st.session_state.login_captcha_input_wider
            entered_captcha_answer_str = current_captcha_input.strip()
            correct_captcha = False
            if not entered_captcha_answer_str: st.error("Por favor, resolva a verificação.")
            else:
                try:
                    if int(entered_captcha_answer_str) == st.session_state.get("captcha_answer"): correct_captcha = True
                    else: st.error("Resposta da verificação incorreta."); generate_captcha(); st.rerun()
                except ValueError: st.error("Resposta da verificação inválida. Digite apenas números."); generate_captcha(); st.rerun()
                except Exception: st.error("Erro ao processar a verificação. Tente novamente."); generate_captcha(); st.rerun()

            if correct_captcha:
                teacher = Teacher.get_by_username(current_login_username) 
                if teacher and bcrypt.checkpw(current_login_password.encode('utf-8'), teacher.password.encode('utf-8')):
                    st.session_state.username = current_login_username; st.session_state.user_type = "teacher"
                    keys_to_clear = ["editing_teacher_username", "teacher_to_remove_confirm", "editing_question_index", "editing_question_data", "captcha_question", "captcha_answer"] 
                    for k in keys_to_clear: 
                        if k in st.session_state: del st.session_state[k]
                    navigate_to("teacher_dashboard"); st.rerun()
                else: st.error("Nome de usuário ou senha incorretos."); generate_captcha(); st.rerun()


def render_teacher_signup(): # Envolve `teacher.save()` que agora usa lock
    st.markdown("<h1 class='title'>📝Cadastro de Professor</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form(key="signup_form_wider_login"): 
            username = st.text_input("Nome de usuário", key="signup_username_wider_login")
            name = st.text_input("Nome completo", key="signup_name_wider_login")
            email = st.text_input("E-mail", key="signup_email_wider_login")
            password = st.text_input("Senha", type="password", key="signup_password_wider_login")
            confirm_password = st.text_input("Confirmar senha", type="password", key="signup_confirm_password_wider_login")
            submit = st.form_submit_button("Cadastrar", use_container_width=True)

            if submit:
                if not (username and name and email and password and confirm_password): st.error("Preencha todos os campos.")
                elif password != confirm_password: st.error("As senhas não coincidem.")
                elif len(password) < 8: st.error("A senha deve ter pelo menos 8 caracteres.")
                elif Teacher.get_by_username(username): st.error("Este nome de usuário já está em uso.")
                else:
                    with st.spinner("Cadastrando professor..."): # Adicionado spinner
                        teacher = Teacher.create(username, password, name, email)
                        teacher.save() # Esta chamada agora é protegida por lock
                    st.success("Professor cadastrado com sucesso!")
                    if st.session_state.get("user_type") == "teacher" and st.session_state.get("username") == "professor":
                        navigate_to("teacher_dashboard")
                    else: navigate_to("home")
                    st.rerun()
        # ... (restante da função sem mudanças)
        if st.session_state.get("user_type") == "teacher" and st.session_state.get("username") == "professor":
            if st.button("Voltar ao Painel do Administrador", key="back_to_admin_dash_signup_wider_login", use_container_width=True):
                navigate_to("teacher_dashboard"); st.rerun()
        else: 
            if st.button("Ir para Login", key="exit_to_home_signup_wider_login", use_container_width=True):
                navigate_to("home"); st.rerun()


def render_edit_teacher_form(teacher_username_to_edit): # Envolve `save_all_teachers` que usa lock
    all_teachers_from_disk = load_teachers_from_json() 
    teacher_data_for_form = all_teachers_from_disk.get(teacher_username_to_edit)

    if not teacher_data_for_form: 
        st.error(f"Professor '{teacher_username_to_edit}' não encontrado para edição.")
        if "editing_teacher_username" in st.session_state: del st.session_state.editing_teacher_username
        if st.button("Voltar ao Painel", key=f"back_to_dash_edit_notfound_wider_login_{teacher_username_to_edit}"):
            navigate_to("teacher_dashboard"); st.rerun()
        return

    st.subheader(f"✏️ Editando Professor: {teacher_username_to_edit}")
    with st.form(key=f"edit_teacher_form_wider_login_{teacher_username_to_edit}"):
        new_name = st.text_input("Nome completo", value=teacher_data_for_form.get("name", ""), key=f"edit_name_wider_login_{teacher_username_to_edit}")
        new_email = st.text_input("E-mail", value=teacher_data_for_form.get("email", ""), key=f"edit_email_wider_login_{teacher_username_to_edit}")
        st.text_input("Nome de usuário (não pode ser alterado)", value=teacher_username_to_edit, disabled=True, key=f"edit_uname_wider_login_{teacher_username_to_edit}")
        st.markdown("---"); st.markdown("**Alterar Senha (opcional)**")
        new_password = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password", key=f"edit_pw_wider_login_{teacher_username_to_edit}")
        confirm_new_password = st.text_input("Confirmar Nova Senha", type="password", key=f"edit_cpw_wider_login_{teacher_username_to_edit}")

        col_form_btns1, col_form_btns2 = st.columns(2)
        with col_form_btns1:
            if st.form_submit_button("Salvar Alterações", use_container_width=True, type="primary"):
                error_occurred = False # ... (lógica de validação de senha)
                current_teacher_being_edited = all_teachers_from_disk.get(teacher_username_to_edit, {})
                if new_password:
                    if new_password != confirm_new_password: st.error("As novas senhas não coincidem."); error_occurred = True
                    elif len(new_password) < 8: st.error("A nova senha deve ter pelo menos 8 caracteres."); error_occurred = True
                    else:
                        if not error_occurred: current_teacher_being_edited["password"] = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                if not error_occurred:
                    current_teacher_being_edited["name"] = new_name
                    current_teacher_being_edited["email"] = new_email
                    with st.spinner("Salvando alterações..."): # Adicionado spinner
                        saved_ok = save_all_teachers(all_teachers_from_disk) # Usa lock e invalida cache
                    if saved_ok:
                        st.success(f"Professor '{teacher_username_to_edit}' atualizado com sucesso!")
                        if new_password and not (new_password != confirm_new_password or len(new_password) < 8) : st.info("A senha foi alterada.")
                        if "editing_teacher_username" in st.session_state: del st.session_state.editing_teacher_username
                        st.rerun()
                    else: st.error("Falha ao salvar as alterações.")
        with col_form_btns2:
            if st.form_submit_button("Cancelar", use_container_width=True):
                if "editing_teacher_username" in st.session_state: del st.session_state.editing_teacher_username
                st.rerun()

def render_edit_question_form(): # Envolve `teacher.save()` que usa lock
    if "editing_question_index" not in st.session_state or "editing_question_data" not in st.session_state:
        # ... (lógica de erro - sem mudança)
        st.error("Erro: Nenhuma pergunta selecionada para edição.")
        if "editing_question_index" in st.session_state: del st.session_state.editing_question_index
        if "editing_question_data" in st.session_state: del st.session_state.editing_question_data
        if st.button("Voltar para Gerenciar Perguntas", key="back_edit_q_err_wider_login"):
            if "editing_question_index" in st.session_state: del st.session_state.editing_question_index
            if "editing_question_data" in st.session_state: del st.session_state.editing_question_data
            st.rerun() 
        return
    # ... (restante da lógica do formulário - sem mudança)
    q_idx = st.session_state.editing_question_index; q_data = st.session_state.editing_question_data 
    st.subheader(f"✏️ Editando Pergunta {q_idx + 1}")
    with st.form(key=f"edit_question_form_wider_login_{q_idx}"):
        edited_question_text = st.text_area("Texto da pergunta", value=q_data["question"], key=f"edit_q_text_wider_login_{q_idx}")
        edited_options = [st.text_input(f"Opção {i+1}", value=(q_data["options"][i] if i < len(q_data["options"]) else ""), key=f"edit_q_opt_wider_login_{q_idx}_{i}") for i in range(4)]
        default_radio_index = q_data.get("correct", 0); 
        if not (0 <= default_radio_index < len(edited_options)): default_radio_index = 0
        edited_correct_answer_index = st.radio("Resposta correta", options=list(range(len(edited_options))), format_func=lambda x: f"Opção {x+1}: {edited_options[x][:30]}{'...' if len(edited_options[x]) > 30 else ''}", index=default_radio_index, horizontal=True, key=f"edit_q_correct_idx_wider_login_{q_idx}")
        submit_edit_q = st.form_submit_button("Salvar Alterações da Pergunta", use_container_width=True, type="primary")
        cancel_edit_q = st.form_submit_button("Cancelar Edição", use_container_width=True)
        if submit_edit_q:
            if not edited_question_text.strip() or not all(opt.strip() for opt in edited_options): st.error("Preencha o texto da pergunta e todas as 4 opções.")
            else:
                st.session_state.temp_questions[q_idx] = {"question": edited_question_text.strip(), "options": [opt.strip() for opt in edited_options], "correct": edited_correct_answer_index}
                if st.session_state.username != "professor":
                    teacher_to_update = Teacher.get_by_username(st.session_state.username) 
                    if teacher_to_update:
                        teacher_to_update.questions = st.session_state.temp_questions
                        with st.spinner("Salvando pergunta..."): # Adicionado spinner
                            teacher_to_update.save() 
                st.success(f"Pergunta {q_idx + 1} atualizada com sucesso!")
                del st.session_state.editing_question_index; del st.session_state.editing_question_data
                st.rerun() 
        if cancel_edit_q: del st.session_state.editing_question_index; del st.session_state.editing_question_data; st.rerun() 

def render_upload_questions_json_page(): # Envolve `teacher.save()` que usa lock
    st.markdown("<h1 class='title'>📤 Carregar Perguntas de Arquivo JSON</h1>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Escolha um arquivo JSON", type=["json"], key="questions_json_uploader")
    if uploaded_file is not None:
        try:
            # ... (lógica de validação do JSON - sem mudança)
            file_content = uploaded_file.read().decode("utf-8"); loaded_questions = json.loads(file_content)
            if not isinstance(loaded_questions, list): st.error("JSON deve ser uma lista."); return
            valid_questions = []; validation_passed = True
            for i, q_data in enumerate(loaded_questions):
                if not (isinstance(q_data, dict) and all(k in q_data for k in ["question", "options", "correct"]) and \
                        isinstance(q_data["question"], str) and q_data["question"].strip() and \
                        isinstance(q_data["options"], list) and len(q_data["options"]) == 4 and \
                        all(isinstance(opt, str) and opt.strip() for opt in q_data["options"]) and \
                        isinstance(q_data["correct"], int) and (0 <= q_data["correct"] < 4)):
                    st.error(f"Erro de formato na pergunta {i+1}. Verifique a estrutura, tipos e se todos os campos estão preenchidos."); validation_passed = False; break
                valid_questions.append({"question": q_data["question"].strip(), "options": [opt.strip() for opt in q_data["options"]], "correct": q_data["correct"]})
            
            if validation_passed:
                st.session_state.temp_questions = valid_questions
                if st.session_state.username != "professor":
                    teacher = Teacher.get_by_username(st.session_state.username) 
                    if teacher:
                        teacher.questions = st.session_state.temp_questions
                        with st.spinner("Salvando perguntas carregadas..."): # Adicionado spinner
                            teacher.save() 
                st.success(f"{len(valid_questions)} perguntas carregadas e validadas com sucesso!")
        except json.JSONDecodeError: st.error("Arquivo JSON inválido.")
        except Exception as e: st.error(f"Erro ao processar arquivo: {e}")
    if st.button("Voltar ao Painel do Professor", key="back_to_dashboard_from_upload"): navigate_to("teacher_dashboard"); st.rerun()


def render_teacher_dashboard(): # Envolve `game.save()` e `teacher.save()` que usam lock
    st.markdown("<h1 class='title'>🖥️ Painel do Professor</h1>", unsafe_allow_html=True)
    if st.session_state.get("editing_teacher_username"): render_edit_teacher_form(st.session_state.editing_teacher_username); return 
    if "editing_question_index" in st.session_state and st.session_state.editing_question_index is not None and st.session_state.page == "teacher_dashboard":
        render_edit_question_form(); return

    teacher_games = Game.get_by_teacher(st.session_state.username) 
    active_games = [g for g in teacher_games if g.status in ["waiting", "active"]]
    if active_games:
        st.subheader("Jogos ativos")
        for game_obj in active_games: 
            if st.button(f"Jogo {game_obj.code} - {len(game_obj.players)} jogadores", key=f"control_game_dash_key_wider_login_{game_obj.code}"):
                st.session_state.game_code = game_obj.code; navigate_to("teacher_game_control"); st.rerun()
    
    if "temp_questions" not in st.session_state or st.session_state.get("user_for_temp_q_wider_login") != st.session_state.username:
        # ... (lógica de carregamento de temp_questions - sem mudança)
        current_teacher = Teacher.get_by_username(st.session_state.username)
        if st.session_state.username == "professor" and not (current_teacher and current_teacher.questions):
             st.session_state.temp_questions = list(SAMPLE_QUESTIONS) 
        elif current_teacher: st.session_state.temp_questions = list(current_teacher.questions) if current_teacher.questions else list(SAMPLE_QUESTIONS)
        else: st.session_state.temp_questions = list(SAMPLE_QUESTIONS)
        st.session_state.user_for_temp_q_wider_login = st.session_state.username

    tab1_title = "Ações e Gerenciamento" if st.session_state.username == "professor" else "Ações do Jogo"
    tab1, tab2 = st.tabs([tab1_title, "Gerenciar Perguntas"]) 

    with tab1: # Admin actions
        if st.session_state.username == "professor": 
            col_admin_actions, col_admin_teacher_list = st.columns([1, 2])
            with col_admin_actions: # ... (botões admin - Criar Jogo envolve game.save())
                if st.button("Criar Novo Jogo (Admin)", key="admin_create_game_btn_wider_login", use_container_width=True, disabled=not bool(st.session_state.temp_questions)):
                    if not st.session_state.temp_questions: st.warning("Carregue perguntas em 'Gerenciar Perguntas'.")
                    else:
                        with st.spinner("Criando novo jogo..."): # Adicionado spinner
                            game_code = generate_game_code()
                            while Game.get_by_code(game_code): game_code = generate_game_code() 
                            new_game = Game(game_code, st.session_state.username, st.session_state.temp_questions)
                            new_game.save() 
                        st.session_state.game_code = new_game.code; navigate_to("teacher_game_control"); st.rerun()
                if st.button("Cadastrar Novo Professor", key="admin_signup_prof_btn_wider_login", use_container_width=True): navigate_to("teacher_signup"); st.rerun()
                if st.button("Sair (Admin)", key="admin_logout_btn_wider_login", use_container_width=True): 
                    for key in list(st.session_state.keys()): del st.session_state[key]; navigate_to("home"); st.rerun()
            with col_admin_teacher_list: # ... (gerenciamento de professores - save_all_teachers)
                if "teacher_to_remove_confirm" in st.session_state:
                    # ... (lógica de confirmação de remoção - save_all_teachers é usado)
                    teacher_to_remove = st.session_state.teacher_to_remove_confirm
                    st.warning(f"Tem certeza que deseja remover '{teacher_to_remove}'?")
                    r_col1, r_col2 = st.columns(2)
                    with r_col1:
                        if st.button("Sim, Remover", key=f"confirm_remove_wider_login_{teacher_to_remove}", type="primary", use_container_width=True):
                            all_teachers_data_disk = load_teachers_from_json() 
                            if teacher_to_remove in all_teachers_data_disk:
                                del all_teachers_data_disk[teacher_to_remove]
                                with st.spinner(f"Removendo professor {teacher_to_remove}..."): # Adicionado spinner
                                    if not save_all_teachers(all_teachers_data_disk): st.error("Erro ao salvar remoção.")
                                    else: st.success(f"Professor '{teacher_to_remove}' removido.")
                            if "teacher_to_remove_confirm" in st.session_state: del st.session_state.teacher_to_remove_confirm
                            st.rerun()
                    with r_col2: # ... (botão cancelar remoção)
                        if st.button("Cancelar Remoção", key=f"cancel_remove_wider_login_{teacher_to_remove}", use_container_width=True):
                            if "teacher_to_remove_confirm" in st.session_state: del st.session_state.teacher_to_remove_confirm
                            st.rerun()
                    st.divider()
                # ... (listagem de professores para gerenciar - sem mudança direta de lock aqui)
                all_teachers_disk_view = load_teachers_from_json(); teachers_to_manage = {u: i for u, i in all_teachers_disk_view.items() if u != "professor"}
                if not teachers_to_manage: st.info("Nenhum outro professor cadastrado.")
                else:
                    for uname, uinfo in teachers_to_manage.items():
                        st.markdown(f"**Nome:** {uinfo.get('name', 'N/A')} (`{uname}`), **Email:** {uinfo.get('email', 'N/A')}")
                        bc1, bc2 = st.columns(2)
                        if bc1.button("✏️ Editar", key=f"admin_edit_btn_wider_login_{uname}", use_container_width=True): st.session_state.editing_teacher_username = uname; st.rerun()
                        if bc2.button("🗑️ Remover", key=f"admin_remove_btn_wider_login_{uname}", type="secondary", use_container_width=True): st.session_state.teacher_to_remove_confirm = uname; st.rerun()
                        st.divider()
        else: # Professor não-admin
            # ... (botões Criar Jogo e Sair - Criar Jogo envolve game.save())
            if st.button("Criar novo jogo", key="std_teacher_create_game_btn_wider_login", use_container_width=True, disabled=not bool(st.session_state.temp_questions)):
                if not bool(st.session_state.temp_questions): st.warning("Adicione perguntas em 'Gerenciar Perguntas'.")
                else:
                    with st.spinner("Criando novo jogo..."): # Adicionado spinner
                        game_code = generate_game_code()
                        while Game.get_by_code(game_code): game_code = generate_game_code()
                        new_game_std = Game(game_code, st.session_state.username, st.session_state.temp_questions)
                        new_game_std.save()
                    st.session_state.game_code = new_game_std.code; navigate_to("teacher_game_control"); st.rerun()
            if st.button("Sair para Home", key="std_teacher_logout_btn_wider_login", use_container_width=True):
                keys_to_clear = ["username", "user_type", "game_code", "temp_questions", "user_for_temp_q_wider_login", "editing_question_index", "editing_question_data"] 
                for k in keys_to_clear: 
                    if k in st.session_state: del st.session_state[k]
                navigate_to("home"); st.rerun()
    with tab2: # Gerenciar Perguntas
        # ... (botão Carregar JSON - já tem spinner em render_upload_questions_json_page)
        # ... (listagem e adição de perguntas - já tem spinner em render_edit_question_form e no form de adicionar)
        st.subheader("Minhas perguntas"); st.markdown("---")
        if st.button("📤 Carregar Perguntas de Arquivo JSON", key="nav_to_upload_json_btn", use_container_width=True): navigate_to("teacher_upload_json"); st.rerun()
        st.markdown("---")
        if not ("editing_question_index" in st.session_state and st.session_state.editing_question_index is not None) :
            if not st.session_state.temp_questions: st.info("Nenhuma pergunta carregada.")
            for i, question in enumerate(st.session_state.temp_questions):
                with st.expander(f"Pergunta {i+1}: {question['question'][:60]}{'...' if len(question['question']) > 60 else ''}"): 
                    st.write("**Opções:**")
                    for j, option in enumerate(question["options"]): st.write(f"{j+1}. {option}{' ✓ (Correta)' if j == question['correct'] else ''}") 
                    ac1,ac2 = st.columns(2)
                    if ac1.button("✏️ Editar Pergunta", key=f"edit_q_btn_tab2_wider_login_{i}", use_container_width=True): st.session_state.editing_question_index = i; st.session_state.editing_question_data = dict(st.session_state.temp_questions[i]); st.rerun()
                    if ac2.button("🗑️ Remover Pergunta", key=f"remove_q_btn_tab2_key_wider_login_{i}", type="secondary", use_container_width=True):
                        st.session_state.temp_questions.pop(i)
                        if st.session_state.username != "professor": 
                            teacher_to_save_q_tab2_rem = Teacher.get_by_username(st.session_state.username)
                            if teacher_to_save_q_tab2_rem:
                                teacher_to_save_q_tab2_rem.questions = st.session_state.temp_questions
                                with st.spinner("Removendo pergunta..."): teacher_to_save_q_tab2_rem.save() # Adicionado spinner
                        st.success("Pergunta removida!"); st.rerun()
            st.subheader("Adicionar nova pergunta")
            with st.form(key="add_new_q_form_key_wider_login", clear_on_submit=True):
                # ... (form de adicionar pergunta - já tem spinner)
                question_text = st.text_area("Texto da pergunta", key="new_q_text_input_wider_login") 
                options_list_inputs = [st.text_input(f"Opção {k+1}", key=f"new_q_opt_wider_login_{k}") for k in range(4)]
                options_for_radio_display = [opt if opt.strip() else f"Opção {idx+1} (vazia)" for idx, opt in enumerate(options_list_inputs)]
                correct_answer_label = None
                if any(opt.strip() for opt in options_list_inputs): correct_answer_label = st.radio("Resposta correta", options=options_for_radio_display, horizontal=True, key="new_q_correct_radio_wider_login")
                else: st.caption("Preencha as opções para selecionar a correta.")
                if st.form_submit_button("Adicionar pergunta", use_container_width=True):
                    if question_text.strip() and all(opt.strip() for opt in options_list_inputs) and correct_answer_label:
                        try:
                            correct_index = options_for_radio_display.index(correct_answer_label)
                            new_question = {"question": question_text.strip(), "options": [opt.strip() for opt in options_list_inputs], "correct": correct_index}
                            st.session_state.temp_questions.append(new_question)
                            if st.session_state.username != "professor": 
                                teacher_save_final_q_add = Teacher.get_by_username(st.session_state.username)
                                if teacher_save_final_q_add:
                                    teacher_save_final_q_add.questions = st.session_state.temp_questions
                                    with st.spinner("Adicionando pergunta..."): teacher_save_final_q_add.save() # Adicionado spinner
                            st.success("Pergunta adicionada!"); st.rerun() 
                        except ValueError: st.error("Erro ao processar resposta correta.")
                    else: st.error("Preencha todos os campos da pergunta.")

def render_teacher_game_control(): # Envolve `game.save()`, `game.start_game()`, `game.next_question()`
    current_game = Game.get_by_code(st.session_state.game_code) 
    if not current_game: st.error("Jogo não encontrado!"); navigate_to("teacher_dashboard"); st.rerun(); return

    st.markdown("<h1 class='title'>🎮Controle do Jogo</h1>", unsafe_allow_html=True)
    if st.button("Voltar ao painel", key="gctrl_back_to_dash_btn_wider_login"): navigate_to("teacher_dashboard"); st.rerun()
    game_action_cols = st.columns(2) 
    with game_action_cols[0]:
        if current_game.status == "waiting":
            if st.button("Iniciar jogo", disabled=len(current_game.players) == 0, key="gctrl_start_game_btn_wider_login", use_container_width=True, type="primary"): 
                with st.spinner("Iniciando jogo..."): current_game.start_game() # Adicionado spinner
                st.rerun()
        elif current_game.status == "active":
            if st.button("▶️ Próxima pergunta", key="gctrl_next_q_btn_wider_login", use_container_width=True, type="primary"): 
                with st.spinner("Carregando próxima pergunta..."): # Adicionado spinner
                    proceed = current_game.next_question()
                if proceed: st.session_state.show_ranking = True; st.rerun()
                else: navigate_to("game_results"); st.rerun()
    with game_action_cols[1]:
        if current_game.status != "finished":
            if st.button("⏹️ Finalizar Jogo", key="gctrl_finish_game_btn_wider_login", use_container_width=True): 
                with st.spinner("Finalizando jogo..."): # Adicionado spinner
                    current_game.status = "finished"; current_game.save()
                navigate_to("game_results"); st.rerun()
        else: 
            if st.button("🏆 Ver Resultados Finais", key="gctrl_view_results_btn_wider_login", use_container_width=True): navigate_to("game_results"); st.rerun()
    # ... (restante da função - display de informações - sem mudança de lock)
    st.divider(); main_game_info_cols = st.columns([2, 1]) 
    with main_game_info_cols[0]:
        st.header(f"🔑Código: `{current_game.code}`"); st.caption(f"Status: {current_game.status.capitalize()}")
        if current_game.status == "waiting":
            st.subheader("Jogadores na sala:"); player_list_placeholder = st.empty() 
            with player_list_placeholder.container():
                if not current_game.players: st.info("Nenhum jogador entrou.")
                else: 
                    player_display_cols = st.columns(3)
                    for i, (pname, pdata) in enumerate(list(current_game.players.items())):
                        with player_display_cols[i % 3]: st.markdown(f"<div style='text-align:center; padding:10px; margin:5px; background-color:#e0f7fa; border-radius:10px;'><span style='font-size:2rem;'>{pdata['icon']}</span><br>{pname}</div>", unsafe_allow_html=True)
        elif current_game.status == "active":
            # ... (display da pergunta atual - sem mudança)
            q_idx = current_game.current_question; st.markdown(f"**Pergunta {q_idx + 1} de {len(current_game.questions)}:**"); q_data = current_game.questions[q_idx]
            st.markdown(f"### {q_data['question']}"); st.write("**Opções:**")
            for i, opt in enumerate(q_data["options"]): st.markdown(f"<span style{'=\'color:green; font-weight:bold;\'' if i == q_data['correct'] else ''}>{i+1}. {opt}{' (Correta)' if i == q_data['correct'] else ''}</span>", unsafe_allow_html=True)
            answered_count = sum(1 for pdata_ans in current_game.players.values() if any(ans.get('question') == q_idx for ans in pdata_ans.get('answers', [])))
            st.info(f"{answered_count} de {len(current_game.players)} jogadores responderam.")
        elif current_game.status == "finished": st.success("🎉 Jogo finalizado!")
    with main_game_info_cols[1]: 
        st.subheader("🏆 Ranking atual") # ... (display do ranking - sem mudança)
        ranking_data = current_game.get_ranking()
        if not ranking_data: st.info("Nenhum jogador pontuou.")
        else:
            for i_rank, p_rank_info in enumerate(ranking_data[:10]): 
                medal = ["🥇", "🥈", "🥉"][i_rank] if i_rank < 3 else f"{i_rank+1}."
                bg, border = ('#f9f9f9', '#eee')
                if i_rank == 0: bg, border = '#FFFACD', '#FFD700' 
                elif i_rank == 1: bg, border = '#F0F8FF', '#ADD8E6' 
                elif i_rank == 2: bg, border = '#FFE4E1', '#FFB6C1' 
                st.markdown(f"""<div style='display:flex;align-items:center;padding:8px;margin-bottom:5px;background-color:{bg};border-radius:8px;border:1px solid {border};box-shadow:0 2px 4px rgba(0,0,0,0.05);'><span style='font-weight:bold;margin-right:12px;font-size:1.1em;width:30px;text-align:center;'>{medal}</span><span style='font-size:1.6rem;margin-right:10px;'>{p_rank_info['icon']}</span><span style='flex-grow:1;font-weight:500;color:#333;'>{p_rank_info['name']}</span><span style='font-weight:bold;color:#007bff;'>{p_rank_info['score']} pts</span></div>""", unsafe_allow_html=True)
    if current_game and current_game.status in ["waiting", "active"]: time.sleep(3); st.rerun()