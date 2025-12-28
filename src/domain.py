from ortools.sat.python import cp_model
import calendar
import pandas as pd

def gerar_estatisticas_detalhadas(solver, escala, residentes, dias, unidades, ano, mes):
    estatisticas = []
    # Usamos os mesmos nomes que o calendar.weekday usa
    dias_nomes_abrev = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    for r in residentes:
        # 1. Criamos o dicionário base
        dados_r = {"Residente": r, "Total Horas": 0}
        
        # 2. Criamos as chaves das unidades dinamicamente baseadas na lista 'unidades'
        for u in unidades:
            dados_r[u] = 0
            
        # 3. Criamos as chaves dos dias da semana
        for nome in dias_nomes_abrev:
            dados_r[nome] = 0

        # 4. Processamos os dados
        for d in dias:
            dia_semana_idx = calendar.weekday(ano, mes, d)
            nome_dia = dias_nomes_abrev[dia_semana_idx]
            
            for t_idx in [0, 1, 2]:
                peso_hora = 12 if t_idx == 2 else 6
                for u in unidades:
                    # Se a variável de decisão for 1 (True)
                    if solver.Value(escala[(r, d, t_idx, u)]) > 0.5:
                        dados_r["Total Horas"] += peso_hora
                        # Esta linha agora é segura, pois a chave u foi criada no passo 2
                        dados_r[u] += 1        
                        dados_r[nome_dia] += 1 

        estatisticas.append(dados_r)
    
    return pd.DataFrame(estatisticas)


def resident_scheduling(ano, mes, num_residentes, lista_r5):
    # Instanciar as variáveis de tempo e estrutura
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dias = range(1, ultimo_dia + 1)
    residentes = range(1, num_residentes + 1)
    turnos = [0, 1, 2] # 0: Manhã, 1: Tarde, 2: Noite
    unidades = ['Clinica', 'Cirurgica']
    dias_nomes = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

    model = cp_model.CpModel()

    # Criar matriz de variáveis de decisão
    escala = {}
    for r in residentes:
        for d in dias:
            for t in turnos:
                for u in unidades:
                    escala[(r, d, t, u)] = model.NewBoolVar(f'r{r}_d{d}_t{t}_u{u}')

    # --- 1. RESTRIÇÕES RÍGIDAS ---
    for d in dias:
        dia_semana_idx = calendar.weekday(ano, mes, d)
        is_fds = dia_semana_idx >= 5 
        
        for r in residentes:
            # Impede o residente de estar em duas UTIs ao mesmo tempo
            for t in turnos:
                model.Add(sum(escala[(r, d, t, u)] for u in unidades) <= 1)

            # Máximo 12h/dia
            trabalho_dia = sum(escala[(r, d, 0, u)] for u in unidades) + \
                           sum(escala[(r, d, 1, u)] for u in unidades) + \
                           (2 * sum(escala[(r, d, 2, u)] for u in unidades))
            model.Add(trabalho_dia <= 2)
            
            # Folga pós-noite
            if d < ultimo_dia:
                fez_noite = sum(escala[(r, d, 2, u)] for u in unidades)
                model.Add(fez_noite + sum(escala[(r, d+1, 0, u)] for u in unidades) <= 1)
                model.Add(fez_noite + sum(escala[(r, d+1, 1, u)] for u in unidades) <= 1)

            # R5 não trabalha FDS
            if is_fds and r in lista_r5:
                for t in turnos:
                    for u in unidades:
                        model.Add(escala[(r, d, t, u)] == 0)

    # --- 2. SOFT CONSTRAINTS (Metas de Equipe) ---
    penalidades = []
    for d in dias:
        dia_semana_idx = calendar.weekday(ano, mes, d)
        is_fds = dia_semana_idx >= 5
        
        metas = {
            'Clinica': {'m': (4, 6) if not is_fds else (2, 3), 
                        't': (2, 4) if not is_fds else (2, 3), 
                        'n': (0, 1)},
            'Cirurgica': {'m': (2, 3) if not is_fds else (1, 2), 
                          't': (2, 3) if not is_fds else (1, 2), 
                          'n': (0, 1)}
        }

        for u in unidades:
            for t_idx, chave in enumerate(['m', 't', 'n']):
                min_pref, max_pref = metas[u][chave]
                soma_turno = sum(escala[(r, d, t_idx, u)] for r in residentes)
                
                sub = model.NewIntVar(0, num_residentes, f'sub_{d}_{t_idx}_{u}')
                sup = model.NewIntVar(0, num_residentes, f'sup_{d}_{t_idx}_{u}')
                
                model.Add(soma_turno + sub >= min_pref)
                model.Add(soma_turno - sup <= max_pref)
                
                penalidades.append(sub * 100)
                penalidades.append(sup * 100)

    # --- 3. SOFT CONSTRAINTS (Carga Horária) ---
    min_h_mes = int((48 * ultimo_dia) / 7)
    max_h_mes = int((54 * ultimo_dia) / 7)

    for r in residentes:
        horas = sum(escala[(r, d, 0, u)]*6 + escala[(r, d, 1, u)]*6 + escala[(r, d, 2, u)]*12 
                    for d in dias for u in unidades)
        falta_h = model.NewIntVar(0, 250, f'falta_h_{r}')
        excesso_h = model.NewIntVar(0, 250, f'excesso_h_{r}')
        
        model.Add(horas + falta_h >= min_h_mes)
        model.Add(horas - excesso_h <= max_h_mes)
        
        penalidades.append(falta_h * 1)
        penalidades.append(excesso_h * 1)

    # Solver
    model.Minimize(sum(penalidades))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 300.0
    status = solver.Solve(model)

    # --- 4. RESULTADO FINAL ---
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        # Gera o relatório de estatísticas primeiro
        df_stats = gerar_estatisticas_detalhadas(solver, escala, residentes, dias, unidades, ano, mes)
        
        # Gera a tabela visual da escala
        dados_agrupados = []
        for d in dias:
            dia_semana_nome = dias_nomes[calendar.weekday(ano, mes, d)]
            for t_nome, t_idx in [('Manhã', 0), ('Tarde', 1), ('Noite', 2)]:
                res_clinica = [str(r) for r in residentes if solver.Value(escala[(r, d, t_idx, 'Clinica')])]
                res_cirurgica = [str(r) for r in residentes if solver.Value(escala[(r, d, t_idx, 'Cirurgica')])]
                
                dados_agrupados.append({
                    "Dia": f"{d:02d}/{mes:02d}",
                    "Dia da Semana": dia_semana_nome,
                    "Turno": t_nome,
                    "UTI Clínica": ", ".join(res_clinica) if res_clinica else "-",
                    "UTI Cirúrgica": ", ".join(res_cirurgica) if res_cirurgica else "-"
                })
        return pd.DataFrame(dados_agrupados), df_stats
    else:
        return None, None
