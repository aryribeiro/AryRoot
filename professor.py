# professor.py
import streamlit as st
from core import Teacher, Game, generate_game_code, SAMPLE_QUESTIONS, DATABASE_PATH
import bcrypt
import json
import os
import random
import time

def navigate_to(page):
    st.session_state.page = page

# Captcha Logic (sem mudanças)
def generate_captcha():
    num1 = random.randint(1, 10); num2 = random.randint(1, 10)
    operation = random.choice(["+", "-"]);
    if operation == "+": question, answer = f"{num1} + {num2}?", num1 + num2
    else:
        if num1 < num2: num1, num2 = num2, num1
        question, answer = f"{num1} - {num2}?", num1 - num2
    st.session_state.captcha_question, st.session_state.captcha_answer = question, answer

def render_teacher_login():
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
                if teacher and teacher.password and bcrypt.checkpw(current_login_password.encode('utf-8'), teacher.password.encode('utf-8')):
                    st.session_state.username = current_login_username
                    st.session_state.user_type = "teacher"
                    keys_to_clear = ["editing_teacher_username", "teacher_to_remove_confirm",
                                     "editing_question_index", "editing_question_data",
                                     "captcha_question", "captcha_answer",
                                     "login_username_captcha_wider", "login_password_captcha_wider",
                                     "login_captcha_input_wider"]
                    for k in keys_to_clear:
                        if k in st.session_state: del st.session_state[k]
                    navigate_to("teacher_dashboard")
                    st.rerun()
                else: st.error("Nome de usuário ou senha incorretos."); generate_captcha(); st.rerun()


def render_teacher_signup():
    st.markdown("<h1 class='title'>📝Cadastro de Professor</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form(key="signup_form_wider_login", clear_on_submit=True):
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
                    with st.spinner("Cadastrando professor..."):
                        teacher = Teacher.create(username, password, name, email)
                        teacher.save()
                    st.success("Professor cadastrado com sucesso!")

                    if st.session_state.get("user_type") == "teacher" and st.session_state.get("username") == "professor":
                        navigate_to("teacher_dashboard")
                    else: navigate_to("home")
                    st.rerun()

        if st.session_state.get("user_type") == "teacher" and st.session_state.get("username") == "professor":
            if st.button("Voltar ao Painel do Administrador", key="back_to_admin_dash_signup_wider_login", use_container_width=True):
                navigate_to("teacher_dashboard"); st.rerun()
        else:
            if st.button("Ir para Login", key="exit_to_home_signup_wider_login", use_container_width=True):
                navigate_to("home"); st.rerun()


def render_edit_teacher_form(teacher_username_to_edit):
    teacher_to_edit = Teacher.get_by_username(teacher_username_to_edit)

    if not teacher_to_edit:
        st.error(f"Professor '{teacher_username_to_edit}' não encontrado para edição.")
        if "editing_teacher_username" in st.session_state: del st.session_state.editing_teacher_username
        if st.button("Voltar ao Painel", key=f"back_to_dash_edit_notfound_wider_login_{teacher_username_to_edit}"):
            navigate_to("teacher_dashboard"); st.rerun()
        return

    st.subheader(f"✏️ Editando Professor: {teacher_username_to_edit}")
    with st.form(key=f"edit_teacher_form_wider_login_{teacher_username_to_edit}"):
        new_name = st.text_input("Nome completo", value=teacher_to_edit.name, key=f"edit_name_wider_login_{teacher_username_to_edit}")
        new_email = st.text_input("E-mail", value=teacher_to_edit.email, key=f"edit_email_wider_login_{teacher_username_to_edit}")
        st.text_input("Nome de usuário (não pode ser alterado)", value=teacher_username_to_edit, disabled=True, key=f"edit_uname_wider_login_{teacher_username_to_edit}")
        st.markdown("---"); st.markdown("**Alterar Senha (opcional)**")
        new_password = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password", key=f"edit_pw_wider_login_{teacher_username_to_edit}")
        confirm_new_password = st.text_input("Confirmar Nova Senha", type="password", key=f"edit_cpw_wider_login_{teacher_username_to_edit}")

        col_form_btns1, col_form_btns2 = st.columns(2)
        with col_form_btns1:
            if st.form_submit_button("Salvar Alterações", use_container_width=True, type="primary"):
                error_occurred = False
                teacher_to_edit.name = new_name
                teacher_to_edit.email = new_email

                if new_password:
                    if new_password != confirm_new_password: st.error("As novas senhas não coincidem."); error_occurred = True
                    elif len(new_password) < 8: st.error("A nova senha deve ter pelo menos 8 caracteres."); error_occurred = True
                    else:
                        teacher_to_edit.password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

                if not error_occurred:
                    with st.spinner("Salvando alterações..."):
                        teacher_to_edit.save()
                    st.success(f"Professor '{teacher_username_to_edit}' atualizado com sucesso!")
                    if new_password: st.info("A senha foi alterada.")
                    if "editing_teacher_username" in st.session_state: del st.session_state.editing_teacher_username
                    st.rerun()
        with col_form_btns2:
            if st.form_submit_button("Cancelar", use_container_width=True):
                if "editing_teacher_username" in st.session_state: del st.session_state.editing_teacher_username
                st.rerun()

def render_edit_question_form():
    if "editing_question_index" not in st.session_state or "editing_question_data" not in st.session_state:
        st.error("Erro: Nenhuma pergunta selecionada para edição.")
        if "editing_question_index" in st.session_state: del st.session_state.editing_question_index
        if "editing_question_data" in st.session_state: del st.session_state.editing_question_data
        if st.button("Voltar para Gerenciar Perguntas", key="back_edit_q_err_wider_login"):
            if "editing_question_index" in st.session_state: del st.session_state.editing_question_index
            if "editing_question_data" in st.session_state: del st.session_state.editing_question_data
            st.rerun()
        return

    q_idx = st.session_state.editing_question_index
    q_data = st.session_state.editing_question_data
    st.subheader(f"✏️ Editando Pergunta {q_idx + 1}")
    with st.form(key=f"edit_question_form_wider_login_{q_idx}"):
        edited_question_text = st.text_area("Texto da pergunta", value=q_data["question"], key=f"edit_q_text_wider_login_{q_idx}")

        edited_option_values = [st.text_input(f"Opção {i+1}", value=(q_data["options"][i] if i < len(q_data["options"]) else ""), key=f"edit_q_opt_wider_login_{q_idx}_{i}") for i in range(4)]

        default_radio_index = q_data.get("correct", 0)
        if not (0 <= default_radio_index < 4): default_radio_index = 0

        option_indices_edit = list(range(4))

        def format_edit_label(idx):
            text_val = edited_option_values[idx].strip()
            return text_val if text_val else f"Opção {idx + 1}"

        edited_correct_selected_index = st.radio(
            "Resposta correta",
            options=option_indices_edit,
            format_func=format_edit_label,
            index=default_radio_index,
            horizontal=True,
            key=f"edit_q_correct_idx_wider_login_{q_idx}"
        )

        submit_edit_q = st.form_submit_button("Salvar Alterações da Pergunta", use_container_width=True, type="primary")
        cancel_edit_q = st.form_submit_button("Cancelar Edição", use_container_width=True)

        if submit_edit_q:
            if not edited_question_text.strip() or not all(opt.strip() for opt in edited_option_values):
                st.error("Preencha o texto da pergunta e todas as 4 opções.")
            else:
                st.session_state.temp_questions[q_idx] = {
                    "question": edited_question_text.strip(),
                    "options": [opt.strip() for opt in edited_option_values],
                    "correct": edited_correct_selected_index
                }

                if st.session_state.username != "professor":
                    teacher_to_update = Teacher.get_by_username(st.session_state.username)
                    if teacher_to_update:
                        teacher_to_update.questions = st.session_state.temp_questions
                        with st.spinner("Salvando pergunta..."):
                            teacher_to_update.save()

                st.success(f"Pergunta {q_idx + 1} atualizada com sucesso!")
                del st.session_state.editing_question_index
                del st.session_state.editing_question_data
                st.rerun()
        if cancel_edit_q:
            del st.session_state.editing_question_index
            del st.session_state.editing_question_data
            st.rerun()

def render_upload_questions_json_page():
    st.markdown("<h1 class='title'>📤 Carregar Perguntas de Arquivo JSON</h1>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Escolha um arquivo JSON", type=["json"], key="questions_json_uploader")
    if uploaded_file is not None:
        try:
            file_content = uploaded_file.read().decode("utf-8")
            loaded_questions = json.loads(file_content)

            if not isinstance(loaded_questions, list):
                st.error("JSON deve ser uma lista.")
                return

            valid_questions = []
            validation_passed = True
            for i, q_data in enumerate(loaded_questions):
                if not (isinstance(q_data, dict) and \
                        all(k in q_data for k in ["question", "options", "correct"]) and \
                        isinstance(q_data["question"], str) and q_data["question"].strip() and \
                        isinstance(q_data["options"], list) and len(q_data["options"]) == 4 and \
                        all(isinstance(opt, str) and opt.strip() for opt in q_data["options"]) and \
                        isinstance(q_data["correct"], int) and (0 <= q_data["correct"] < 4)):
                    st.error(f"Erro de formato na pergunta {i+1}. Verifique a estrutura, tipos e se todos os campos estão preenchidos.")
                    validation_passed = False
                    break
                valid_questions.append({
                    "question": q_data["question"].strip(),
                    "options": [opt.strip() for opt in q_data["options"]],
                    "correct": q_data["correct"]
                })

            if validation_passed:
                st.session_state.temp_questions = valid_questions
                if st.session_state.username != "professor":
                    teacher = Teacher.get_by_username(st.session_state.username)
                    if teacher:
                        teacher.questions = st.session_state.temp_questions
                        with st.spinner("Salvando perguntas carregadas..."):
                            teacher.save()
                st.success(f"{len(valid_questions)} perguntas carregadas e validadas com sucesso!")
        except json.JSONDecodeError: st.error("Arquivo JSON inválido.")
        except Exception as e: st.error(f"Erro ao processar arquivo: {e}")

    if st.button("Voltar ao Painel do Professor", key="back_to_dashboard_from_upload"):
        navigate_to("teacher_dashboard")
        st.rerun()


def render_teacher_dashboard():
    st.markdown("<h1 class='title'>🖥️ Painel do Professor</h1>", unsafe_allow_html=True)

    if st.session_state.get("editing_teacher_username"):
        render_edit_teacher_form(st.session_state.editing_teacher_username)
        return

    if "editing_question_index" in st.session_state and \
       st.session_state.editing_question_index is not None and \
       st.session_state.page == "teacher_dashboard":
        render_edit_question_form()
        return

    teacher_games = Game.get_by_teacher(st.session_state.username)
    active_games = [g for g in teacher_games if g.status in ["waiting", "active"]]
    if active_games:
        st.subheader("Jogos ativos")
        for game_obj in active_games:
            if st.button(f"Jogo {game_obj.code} - {len(game_obj.players)} jogadores", key=f"control_game_dash_key_wider_login_{game_obj.code}"):
                st.session_state.game_code = game_obj.code
                navigate_to("teacher_game_control")
                st.rerun()

    if "temp_questions" not in st.session_state or st.session_state.get("user_for_temp_q_wider_login") != st.session_state.username:
        current_teacher = Teacher.get_by_username(st.session_state.username)
        if current_teacher:
            st.session_state.temp_questions = list(current_teacher.questions)
        else:
            st.session_state.temp_questions = list(SAMPLE_QUESTIONS) if st.session_state.username == "professor" else []
        st.session_state.user_for_temp_q_wider_login = st.session_state.username

    tab1_title = "Ações e Gerenciamento" if st.session_state.username == "professor" else "Ações do Jogo"
    tab1, tab2 = st.tabs([tab1_title, "Gerenciar Perguntas"])

    with tab1:
        if st.session_state.username == "professor":
            col_admin_actions, col_admin_teacher_list = st.columns([1, 2])
            with col_admin_actions:
                if st.button("Criar Novo Jogo (Admin)", key="admin_create_game_btn_wider_login", use_container_width=True, disabled=not bool(st.session_state.temp_questions)):
                    if not st.session_state.temp_questions:
                        st.warning("Carregue ou adicione perguntas em 'Gerenciar Perguntas' primeiro.")
                    else:
                        with st.spinner("Criando novo jogo..."):
                            game_code = generate_game_code()
                            while Game.get_by_code(game_code): game_code = generate_game_code()
                            new_game = Game(game_code, st.session_state.username, questions_json_str=json.dumps(st.session_state.temp_questions))
                            new_game.save()
                        st.session_state.game_code = new_game.code
                        navigate_to("teacher_game_control")
                        st.rerun()
                if st.button("Cadastrar Novo Professor", key="admin_signup_prof_btn_wider_login", use_container_width=True):
                    navigate_to("teacher_signup")
                    st.rerun()
                if st.button("Sair (Admin)", key="admin_logout_btn_wider_login", use_container_width=True):
                    for key in list(st.session_state.keys()): del st.session_state[key]
                    navigate_to("home")
                    st.rerun()
            with col_admin_teacher_list:
                if "teacher_to_remove_confirm" in st.session_state:
                    teacher_to_remove_username = st.session_state.teacher_to_remove_confirm
                    st.warning(f"Tem certeza que deseja remover o professor '{teacher_to_remove_username}'?")
                    r_col1, r_col2 = st.columns(2)
                    with r_col1:
                        if st.button("Sim, Remover", key=f"confirm_remove_wider_login_{teacher_to_remove_username}", type="primary", use_container_width=True):
                            with st.spinner(f"Removendo professor {teacher_to_remove_username}..."):
                                deleted = Teacher.delete_by_username(teacher_to_remove_username)
                            if deleted:
                                st.success(f"Professor '{teacher_to_remove_username}' removido.")
                            else:
                                st.error(f"Erro ao remover professor '{teacher_to_remove_username}'.")
                            if "teacher_to_remove_confirm" in st.session_state: del st.session_state.teacher_to_remove_confirm
                            st.rerun()
                    with r_col2:
                        if st.button("Cancelar Remoção", key=f"cancel_remove_wider_login_{teacher_to_remove_username}", use_container_width=True):
                            if "teacher_to_remove_confirm" in st.session_state: del st.session_state.teacher_to_remove_confirm
                            st.rerun()
                    st.divider()

                teachers_to_manage = Teacher.get_all_teachers_except_admin()
                if not teachers_to_manage: st.info("Nenhum outro professor cadastrado.")
                else:
                    st.subheader("Gerenciar Professores")
                    for teacher_obj in teachers_to_manage:
                        st.markdown(f"**Nome:** {teacher_obj.name} (`{teacher_obj.username}`), **Email:** {teacher_obj.email}")
                        bc1, bc2 = st.columns(2)
                        if bc1.button("✏️ Editar", key=f"admin_edit_btn_wider_login_{teacher_obj.username}", use_container_width=True):
                            st.session_state.editing_teacher_username = teacher_obj.username
                            st.rerun()
                        if bc2.button("🗑️ Remover", key=f"admin_remove_btn_wider_login_{teacher_obj.username}", type="secondary", use_container_width=True):
                            st.session_state.teacher_to_remove_confirm = teacher_obj.username
                            st.rerun()
                        st.divider()
        else:
            if st.button("Criar novo jogo", key="std_teacher_create_game_btn_wider_login", use_container_width=True, disabled=not bool(st.session_state.temp_questions)):
                if not bool(st.session_state.temp_questions):
                    st.warning("Adicione perguntas em 'Gerenciar Perguntas' primeiro.")
                else:
                    with st.spinner("Criando novo jogo..."):
                        game_code = generate_game_code()
                        while Game.get_by_code(game_code): game_code = generate_game_code()
                        new_game_std = Game(game_code, st.session_state.username, questions_json_str=json.dumps(st.session_state.temp_questions))
                        new_game_std.save()
                    st.session_state.game_code = new_game_std.code
                    navigate_to("teacher_game_control")
                    st.rerun()
            if st.button("Sair para Home", key="std_teacher_logout_btn_wider_login", use_container_width=True):
                keys_to_clear_std_logout = ["username", "user_type", "game_code", "temp_questions",
                                      "user_for_temp_q_wider_login", "editing_question_index",
                                      "editing_question_data"]
                for k_logout in keys_to_clear_std_logout:
                    if k_logout in st.session_state: del st.session_state[k_logout]
                navigate_to("home")
                st.rerun()
    with tab2:
        st.subheader("Minhas perguntas")
        st.markdown("---")
        if st.button("📤 Carregar Perguntas de Arquivo JSON", key="nav_to_upload_json_btn", use_container_width=True):
            navigate_to("teacher_upload_json")
            st.rerun()
        st.markdown("---")

        if not ("editing_question_index" in st.session_state and st.session_state.editing_question_index is not None) :
            if not st.session_state.temp_questions:
                st.info("Nenhuma pergunta carregada. Adicione perguntas manualmente ou carregue um arquivo JSON.")

            for i, question in enumerate(st.session_state.temp_questions):
                with st.expander(f"Pergunta {i+1}: {question['question'][:60]}{'...' if len(question['question']) > 60 else ''}"):
                    st.write("**Opções:**")
                    for j, option in enumerate(question["options"]):
                        st.write(f"{j+1}. {option}{' ✓ (Correta)' if j == question['correct'] else ''}")

                    ac1,ac2 = st.columns(2)
                    if ac1.button("✏️ Editar Pergunta", key=f"edit_q_btn_tab2_wider_login_{i}", use_container_width=True):
                        st.session_state.editing_question_index = i
                        st.session_state.editing_question_data = dict(st.session_state.temp_questions[i])
                        st.rerun()
                    if ac2.button("🗑️ Remover Pergunta", key=f"remove_q_btn_tab2_key_wider_login_{i}", type="secondary", use_container_width=True):
                        st.session_state.temp_questions.pop(i)
                        if st.session_state.username != "professor":
                            teacher_to_save_q_tab2_rem = Teacher.get_by_username(st.session_state.username)
                            if teacher_to_save_q_tab2_rem:
                                teacher_to_save_q_tab2_rem.questions = st.session_state.temp_questions
                                with st.spinner("Removendo pergunta..."):
                                    teacher_to_save_q_tab2_rem.save()
                        st.success("Pergunta removida!")
                        st.rerun()

            st.subheader("Adicionar nova pergunta")
            
            # Gerenciador de chave para o formulário de adicionar pergunta, para forçar reinicialização
            if 'add_q_form_run_count' not in st.session_state:
                st.session_state.add_q_form_run_count = 0
            
            form_key = f"add_new_q_form_key_wider_login_{st.session_state.add_q_form_run_count}"

            with st.form(key=form_key, clear_on_submit=True):
                question_text = st.text_area("Texto da pergunta", key=f"q_text_{form_key}") # Chave dinâmica para input

                options_list_inputs_values = [st.text_input(f"Opção {k+1}", key=f"q_opt_{k}_{form_key}") for k in range(4)] # Chaves dinâmicas

                option_indices = list(range(4))

                def format_add_q_option_label(idx):
                    # Acessa os valores dos inputs de opção usando suas chaves dinâmicas
                    # Isso garante que estamos lendo os valores corretos para ESTA instância do formulário.
                    current_option_val = st.session_state.get(f"q_opt_{idx}_{form_key}", "").strip()
                    return current_option_val if current_option_val else f"Opção {idx + 1}"

                correct_selected_index = st.radio(
                    "Resposta correta",
                    options=option_indices,
                    format_func=format_add_q_option_label,
                    horizontal=True,
                    key=f"q_radio_{form_key}" # Chave dinâmica para radio
                )

                submit_button_add_q = st.form_submit_button("Adicionar pergunta", use_container_width=True)

                if submit_button_add_q:
                    # Re-ler os valores dos inputs usando as chaves dinâmicas para garantir que temos os valores corretos
                    # da instância atual do formulário no momento do submit.
                    current_question_text = st.session_state[f"q_text_{form_key}"]
                    current_options_values = [st.session_state[f"q_opt_{k}_{form_key}"] for k in range(4)]
                    current_correct_index = st.session_state[f"q_radio_{form_key}"]


                    if current_question_text.strip() and \
                       all(opt.strip() for opt in current_options_values):

                        new_question = {
                            "question": current_question_text.strip(),
                            "options": [opt.strip() for opt in current_options_values],
                            "correct": current_correct_index
                        }
                        st.session_state.temp_questions.append(new_question)

                        if st.session_state.username != "professor":
                            teacher_save_final_q_add = Teacher.get_by_username(st.session_state.username)
                            if teacher_save_final_q_add:
                                teacher_save_final_q_add.questions = st.session_state.temp_questions
                                with st.spinner("Adicionando pergunta..."):
                                    teacher_save_final_q_add.save()
                        st.success("Pergunta adicionada!")
                        st.session_state.add_q_form_run_count += 1 # Incrementar para a próxima instância do formulário ser nova
                        st.rerun()
                    else:
                        if not current_question_text.strip():
                            st.error("Preencha o texto da pergunta.")
                        elif not all(opt.strip() for opt in current_options_values):
                            st.error("Preencha todas as 4 opções de resposta.")
                        else:
                             st.error("Preencha todos os campos da pergunta e certifique-se que todas as opções têm texto.")

def render_teacher_game_control():
    current_game_code = st.session_state.get("game_code")
    if not current_game_code:
        st.error("Nenhum código de jogo encontrado na sessão.")
        navigate_to("teacher_dashboard")
        st.rerun()
        return

    current_game = Game.get_by_code(current_game_code)
    if not current_game:
        st.error(f"Jogo com código {current_game_code} não encontrado!")
        navigate_to("teacher_dashboard")
        st.rerun()
        return

    st.markdown("<h1 class='title'>🎮Controle do Jogo</h1>", unsafe_allow_html=True)
    if st.button("Voltar ao painel", key="gctrl_back_to_dash_btn_wider_login"):
        navigate_to("teacher_dashboard")
        st.rerun()

    game_action_cols = st.columns(2)
    with game_action_cols[0]:
        if current_game.status == "waiting":
            if st.button("Iniciar jogo", disabled=len(current_game.players) == 0, key="gctrl_start_game_btn_wider_login", use_container_width=True, type="primary"):
                with st.spinner("Iniciando jogo..."):
                    current_game.start_game()
                st.rerun()
        elif current_game.status == "active":
            if st.button("▶️ Próxima pergunta", key="gctrl_next_q_btn_wider_login", use_container_width=True, type="primary"):
                with st.spinner("Carregando próxima pergunta..."):
                    proceed = current_game.next_question()
                if proceed:
                    st.session_state.show_ranking = True
                    st.rerun()
                else:
                    navigate_to("game_results")
                    st.rerun()
    with game_action_cols[1]:
        if current_game.status != "finished":
            if st.button("⏹️ Finalizar Jogo", key="gctrl_finish_game_btn_wider_login", use_container_width=True):
                with st.spinner("Finalizando jogo..."):
                    current_game.status = "finished"
                    current_game.save()
                navigate_to("game_results")
                st.rerun()
        else:
            if st.button("🏆 Ver Resultados Finais", key="gctrl_view_results_btn_wider_login", use_container_width=True):
                navigate_to("game_results")
                st.rerun()

    st.divider()
    main_game_info_cols = st.columns([2, 1])
    with main_game_info_cols[0]:
        st.header(f"🔑Código: `{current_game.code}`")
        st.caption(f"Status: {current_game.status.capitalize()}")

        if current_game.status == "waiting":
            st.subheader("Jogadores na sala:")
            player_list_placeholder = st.empty()
            with player_list_placeholder.container():
                if not current_game.players: st.info("Nenhum jogador entrou.")
                else:
                    player_display_cols = st.columns(3)
                    for i, (pname, pdata) in enumerate(list(current_game.players.items())):
                        with player_display_cols[i % 3]:
                            st.markdown(f"<div style='text-align:center; padding:10px; margin:5px; background-color:#e0f7fa; border-radius:10px;'><span style='font-size:2rem;'>{pdata.get('icon', '❓')}</span><br>{pname}</div>", unsafe_allow_html=True)

        elif current_game.status == "active":
            q_idx = current_game.current_question
            if 0 <= q_idx < len(current_game.questions):
                st.markdown(f"**Pergunta {q_idx + 1} de {len(current_game.questions)}:**")
                q_data = current_game.questions[q_idx]
                st.markdown(f"### {q_data['question']}")
                st.write("**Opções:**")
                for i, opt in enumerate(q_data["options"]):
                    st.markdown(f"<span style{'=\'color:green; font-weight:bold;\'' if i == q_data['correct'] else ''}>{i+1}. {opt}{' (Correta)' if i == q_data['correct'] else ''}</span>", unsafe_allow_html=True)

                answered_count = sum(1 for pdata_ans in current_game.players.values() if isinstance(pdata_ans, dict) and any(ans.get('question') == q_idx for ans in pdata_ans.get('answers', [])))
                st.info(f"{answered_count} de {len(current_game.players)} jogadores responderam.")
            else:
                st.warning("Índice da pergunta atual fora do intervalo. O jogo pode ter terminado ou há um problema.")

        elif current_game.status == "finished":
            st.success("🎉 Jogo finalizado!")
            st.markdown("Os resultados finais podem ser visualizados na página de resultados.")

    with main_game_info_cols[1]:
        st.subheader("🏆 Ranking atual")
        ranking_data = current_game.get_ranking()
        if not ranking_data: st.info("Nenhum jogador pontuou ainda ou nenhum jogador na partida.")
        else:
            for i_rank, p_rank_info in enumerate(ranking_data[:10]):
                medal = ["🥇", "🥈", "🥉"][i_rank] if i_rank < 3 else f"{i_rank+1}."
                bg, border = ('#f9f9f9', '#eee')
                if i_rank == 0: bg, border = '#FFFACD', '#FFD700'
                elif i_rank == 1: bg, border = '#F0F8FF', '#ADD8E6'
                elif i_rank == 2: bg, border = '#FFE4E1', '#FFB6C1'
                st.markdown(f"""<div style='display:flex;align-items:center;padding:8px;margin-bottom:5px;background-color:{bg};border-radius:8px;border:1px solid {border};box-shadow:0 2px 4px rgba(0,0,0,0.05);'><span style='font-weight:bold;margin-right:12px;font-size:1.1em;width:30px;text-align:center;'>{medal}</span><span style='font-size:1.6rem;margin-right:10px;'>{p_rank_info.get('icon', '❓')}</span><span style='flex-grow:1;font-weight:500;color:#333;'>{p_rank_info['name']}</span><span style='font-weight:bold;color:#007bff;'>{p_rank_info['score']} pts</span></div>""", unsafe_allow_html=True)

    if current_game and current_game.status in ["waiting", "active"]:
        time.sleep(3)
        st.rerun()