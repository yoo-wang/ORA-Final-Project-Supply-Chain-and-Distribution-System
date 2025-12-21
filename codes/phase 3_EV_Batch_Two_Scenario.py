# -*- coding: utf-8 -*-
import gurobipy as gp
from gurobipy import GRB
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import sys, os

# ==========================================
# 0. 繪圖樣式設定 (安全模式)
# ==========================================
try:
    plt.style.use('seaborn-v0_8-whitegrid')
except OSError:
    try:
        plt.style.use('seaborn-whitegrid')
    except OSError:
        plt.style.use('ggplot')

# ==========================================
# 1. 參數定義 (Parameters)
# ==========================================
S_base = 1000.0
V_base = 4.16
Z_base = (V_base ** 2) * 1000 / S_base 

node_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
P_load_kW = {
    1: 0, 2: 66.67, 3: 85, 4: 100, 5: 56.67, 
    6: 76.67, 7: 56.67, 8: 100, 9: 142.67, 10: 0, 
    11: 133.33, 12: 281, 13: 56.67
}
P_load_pu = {i: val / S_base for i, val in P_load_kW.items()}
Q_load_pu = {i: 0 for i in node_ids} 

lines_info = {
    1: (1, 2),   2: (2, 3),   3: (3, 4),   4: (2, 5),   5: (5, 6),
    6: (6, 7),   7: (7, 8),   8: (3, 8),   9: (8, 9),   10: (4, 9),
    11: (2, 10), 12: (10, 11), 13: (11, 12), 14: (12, 13), 15: (3, 13)
}
line_ids = list(lines_info.keys())

R_pu = 0.1 / Z_base; X_pu = 0.1 / Z_base; Big_M = 10.0 

# 投資參數
Cost_DG_kW = 1.5
Cost_Hard_Line = 400.0
Cost_Shedding = 14.0
Budget_H = 1; Budget_G = 1
DG_Cap_kW = 100.0; DG_Cap_pu = DG_Cap_kW / S_base

# ==========================================
# 2. 定義測試情境 (Test Cases)
# ==========================================
test_cases = [
    ("Scenario_1", {
        'S1': {'prob': 0.9, 'attack': [2, 11]},
        'S2': {'prob': 0.1, 'attack': [2, 5, 8, 14, 15]}
    }),
    ("Scenario_2", {
        'S1': {'prob': 0.9, 'attack': [4,6, 11]},
        'S2': {'prob': 0.1, 'attack': [2, 5, 8, 14, 15]}
    }),
    ("Scenario_3", {
        'S1': {'prob': 0.5, 'attack': [2, 11]},
        'S2': {'prob': 0.5, 'attack': [2, 5, 8, 14, 15]}
    }),
    ("Scenario_4", {
        'S1': {'prob': 0.5, 'attack': [4, 6, 11]},
        'S2': {'prob': 0.5, 'attack': [2, 5, 8, 14, 15]}
    }),
    ("Scenario_5", {
        'S1': {'prob': 0.1, 'attack': [2, 11]},
        'S2': {'prob': 0.9, 'attack': [2, 5, 8, 14, 15]}
    }),
    ("Scenario_6", {
        'S1': {'prob': 0.1, 'attack': [4,6, 11]},
        'S2': {'prob': 0.9, 'attack': [2, 5, 8, 14, 15]}
    })
]

# ==========================================
# 3. 攻擊模式編碼與分析工具
# ==========================================
def generate_attack_legend(cases):
    unique_patterns = []
    for _, scens in cases:
        for s_key in scens:
            atk = tuple(sorted(scens[s_key]['attack']))
            if atk not in unique_patterns:
                unique_patterns.append(atk)
    unique_patterns.sort(key=lambda x: (len(x), x))
    
    legend = {}
    pattern_map = {}
    for idx, pat in enumerate(unique_patterns):
        code = chr(65 + idx)
        legend[code] = list(pat)
        pattern_map[pat] = code
    return legend, pattern_map

def print_legend(legend):
    print("\n" + "="*60)
    print(" 攻擊模式代號對照表 (Attack Pattern Legend)")
    print("="*60)
    print(f"{'Code':<6} | {'Lines Attacked (Broken)':<30}")
    print("-" * 60)
    for code, lines in legend.items():
        print(f"{code:<6} | {str(lines)}")
    print("="*60 + "\n")

attack_legend, attack_map = generate_attack_legend(test_cases)

# ==========================================
# 4. 求解函式
# ==========================================
def solve_robust_model(case_name, current_scenarios):
    scenario_keys = list(current_scenarios.keys())
    model = gp.Model(f"Robust_{case_name}")
    model.setParam('OutputFlag', 0) 

    y_h = model.addVars(line_ids, vtype=GRB.BINARY, name="y_h") 
    candidate_nodes = [i for i in node_ids if i != 1]
    y_g = model.addVars(candidate_nodes, vtype=GRB.BINARY, name="y_g") 

    v = model.addVars(line_ids, scenario_keys, vtype=GRB.BINARY, name="v")
    P_flow = model.addVars(line_ids, scenario_keys, lb=-10, ub=10, vtype=GRB.CONTINUOUS)
    Q_flow = model.addVars(line_ids, scenario_keys, lb=-10, ub=10, vtype=GRB.CONTINUOUS)
    U = model.addVars(node_ids, scenario_keys, lb=0.81, ub=1.21, vtype=GRB.CONTINUOUS)
    delta_P = model.addVars(node_ids, scenario_keys, lb=0, vtype=GRB.CONTINUOUS)
    delta_Q = model.addVars(node_ids, scenario_keys, lb=0, vtype=GRB.CONTINUOUS)
    P_gen = model.addVars(candidate_nodes, scenario_keys, lb=0, ub=DG_Cap_pu, vtype=GRB.CONTINUOUS)

    for s in scenario_keys:
        U[1, s].lb = 1.0; U[1, s].ub = 1.0 
        for i in node_ids:
            delta_P[i, s].ub = P_load_pu[i]
            delta_Q[i, s].ub = Q_load_pu[i]

    model.addConstr(gp.quicksum(y_h[l] for l in line_ids) <= Budget_H)
    model.addConstr(gp.quicksum(y_g[i] for i in candidate_nodes) <= Budget_G)

    for s in scenario_keys:
        attack_set = current_scenarios[s]['attack']
        for l in line_ids:
            if l in attack_set: model.addConstr(v[l, s] <= y_h[l])
        for i in candidate_nodes:
            model.addConstr(P_gen[i, s] <= DG_Cap_pu * y_g[i])

        for j in node_ids:
            if j == 1: continue
            inc = gp.quicksum(P_flow[l, s] for l, (u, v_n) in lines_info.items() if v_n == j)
            out = gp.quicksum(P_flow[l, s] for l, (u, v_n) in lines_info.items() if u == j)
            gen = P_gen[j, s] if j in candidate_nodes else 0
            model.addConstr(inc - out + gen == P_load_pu[j] - delta_P[j, s])
            
            inc_q = gp.quicksum(Q_flow[l, s] for l, (u, v_n) in lines_info.items() if v_n == j)
            out_q = gp.quicksum(Q_flow[l, s] for l, (u, v_n) in lines_info.items() if u == j)
            model.addConstr(inc_q - out_q == Q_load_pu[j] - delta_Q[j, s])

        for l in line_ids:
            model.addConstr(P_flow[l, s] <= 10*v[l, s]); model.addConstr(P_flow[l, s] >= -10*v[l, s])
            model.addConstr(Q_flow[l, s] <= 10*v[l, s]); model.addConstr(Q_flow[l, s] >= -10*v[l, s])
            u, v_n = lines_info[l]
            lhs = U[u, s] - U[v_n, s] - 2*(R_pu*P_flow[l, s] + X_pu*Q_flow[l, s])
            model.addConstr(lhs <= Big_M*(1-v[l, s])); model.addConstr(lhs >= -Big_M*(1-v[l, s]))

        model.addConstr(gp.quicksum(v[l, s] for l in line_ids) <= len(node_ids) - 1)

    cost_inv = Cost_Hard_Line * gp.quicksum(y_h[l] for l in line_ids) + \
               (Cost_DG_kW * DG_Cap_kW) * gp.quicksum(y_g[i] for i in candidate_nodes)

    expected_shedding_cost = 0
    for s in scenario_keys:
        prob = current_scenarios[s]['prob']
        loss_s = Cost_Shedding * gp.quicksum(delta_P[i, s] for i in node_ids) * S_base
        switching_s = 0.01 * gp.quicksum(v[l, s] for l in line_ids)
        expected_shedding_cost += prob * (loss_s + switching_s)

    model.setObjective(cost_inv + expected_shedding_cost, GRB.MINIMIZE)
    model.optimize()

    if model.status == GRB.OPTIMAL:
        hardened = [l for l in line_ids if y_h[l].x > 0.5]
        new_dgs = [i for i in candidate_nodes if y_g[i].x > 0.5]
        
        prob1 = current_scenarios['S1']['prob'] if 'S1' in current_scenarios else 1.0
        prob2 = current_scenarios['S2']['prob'] if 'S2' in current_scenarios else 0.0

        return {
            "Case Name": case_name,
            "S1 Prob": prob1, "S2 Prob": prob2,
            "Hardened": hardened, "New DGs": new_dgs,
            "Obj Value": round(model.objVal, 2),
            "Invest ($)": round(cost_inv.getValue(), 2),
        }
    else:
        return None

# ==========================================
# 5. EV 指標計算函式
# ==========================================
def evaluate_fixed_plan(fixed_hardened, fixed_dgs, scenarios):
    scenario_keys = list(scenarios.keys())
    m = gp.Model("Eval_Fixed")
    m.setParam('OutputFlag', 0)
    
    v = m.addVars(line_ids, scenario_keys, vtype=GRB.BINARY)
    P_flow = m.addVars(line_ids, scenario_keys, lb=-10, ub=10)
    Q_flow = m.addVars(line_ids, scenario_keys, lb=-10, ub=10)
    U = m.addVars(node_ids, scenario_keys, lb=0.81, ub=1.21)
    delta_P = m.addVars(node_ids, scenario_keys, lb=0)
    delta_Q = m.addVars(node_ids, scenario_keys, lb=0)
    P_gen = m.addVars(node_ids, scenario_keys, lb=0, ub=DG_Cap_pu) 
    
    for s in scenario_keys:
        U[1, s].lb=1.0; U[1, s].ub=1.0
        for i in node_ids: delta_P[i, s].ub = P_load_pu[i]; delta_Q[i, s].ub = Q_load_pu[i]

    for s in scenario_keys:
        attack_set = scenarios[s]['attack']
        for l in line_ids:
            is_invested = 1 if l in fixed_hardened else 0
            if l in attack_set: m.addConstr(v[l, s] <= is_invested) 
        for i in node_ids:
            if i==1: continue
            has_dg = 1 if i in fixed_dgs else 0
            m.addConstr(P_gen[i, s] <= DG_Cap_pu * has_dg)

        for j in node_ids:
            if j==1: continue
            inc = gp.quicksum(P_flow[l, s] for l, (u, v_n) in lines_info.items() if v_n == j)
            out = gp.quicksum(P_flow[l, s] for l, (u, v_n) in lines_info.items() if u == j)
            m.addConstr(inc - out + P_gen[j, s] == P_load_pu[j] - delta_P[j, s])
            
            inc_q = gp.quicksum(Q_flow[l, s] for l, (u, v_n) in lines_info.items() if v_n == j)
            out_q = gp.quicksum(Q_flow[l, s] for l, (u, v_n) in lines_info.items() if u == j)
            m.addConstr(inc_q - out_q == Q_load_pu[j] - delta_Q[j, s])
            
        for l in line_ids:
            u, v_n = lines_info[l]
            m.addConstr(P_flow[l, s] <= 10*v[l, s]); m.addConstr(P_flow[l, s] >= -10*v[l, s])
            m.addConstr(Q_flow[l, s] <= 10*v[l, s]); m.addConstr(Q_flow[l, s] >= -10*v[l, s])
            lhs = U[u, s] - U[v_n, s] - 2*(R_pu*P_flow[l, s] + X_pu*Q_flow[l, s])
            m.addConstr(lhs <= Big_M*(1-v[l, s])); m.addConstr(lhs >= -Big_M*(1-v[l, s]))
            
        m.addConstr(gp.quicksum(v[l, s] for l in line_ids) <= len(node_ids)-1)

    fixed_inv_cost = Cost_Hard_Line * len(fixed_hardened) + (Cost_DG_kW * 100.0) * len(fixed_dgs)
    op_cost = 0
    for s in scenario_keys:
        prob = scenarios[s]['prob']
        loss = Cost_Shedding * gp.quicksum(delta_P[i, s] for i in node_ids) * S_base
        switch = 0.01 * gp.quicksum(v[l, s] for l in line_ids)
        op_cost += prob * (loss + switch)
        
    m.setObjective(fixed_inv_cost + op_cost, GRB.MINIMIZE)
    m.optimize()
    return m.objVal if m.status == GRB.OPTIMAL else 9999999.0

def calculate_ev_metrics(case_name, scenarios):
    rp_result = solve_robust_model(case_name, scenarios)
    if not rp_result: return None
    cost_rp = rp_result['Obj Value']
    
    ws_total = 0; max_prob = -1; naive_plan = ([], []) 
    for s_key in scenarios:
        single_scen_input = {s_key: scenarios[s_key].copy()}
        single_scen_input[s_key]['prob'] = 1.0 
        res = solve_robust_model(f"{s_key}_Only", single_scen_input)
        real_prob = scenarios[s_key]['prob']
        ws_total += real_prob * res['Obj Value']
        if real_prob > max_prob:
            max_prob = real_prob
            naive_plan = (res['Hardened'], res['New DGs'])
            
    cost_eev = evaluate_fixed_plan(naive_plan[0], naive_plan[1], scenarios)
    evpi = cost_rp - ws_total
    vss = cost_eev - cost_rp
    
    rp_result.update({"WS": round(ws_total, 2), "EEV": round(cost_eev, 2), "EVPI": round(evpi, 2), "VSS": round(vss, 2)})
    return rp_result

# ==========================================
# 6. Phase 5: 敏感度分析 
# ==========================================
def run_sensitivity_analysis():
    print("\n" + "="*85) # 加寬分隔線
    print("  Phase 5: S2 機率敏感度分析 (0.0 -> 1.0) - 含決策內容對照")
    print("="*85)
    
    # 表格標題 (加入 Hardened 與 New DGs)
    header = (
        f"{'S2 Prob':<8} | {'RP Cost':<9} | {'VSS':<9} | "
        f"{'Hardened':<12} | {'New DGs':<10} | {'Status'}"
    )
    print(header)
    print("-" * 110) # 加長分隔線以容納所有欄位

    base_attack_s1 = [2, 11]
    base_attack_s2 = [2, 5, 8, 14, 15]
    
    sensitivity_results = []
    s2_probs = np.linspace(0.0, 1.0, 11) 
    
    last_decision_str = None
    last_obj_val = -1.0 
    
    # 暫時隱藏詳細計算過程
    original_stdout = sys.stdout
    sys.stdout = open(os.devnull, 'w') 

    for p2 in s2_probs:
        p2 = round(p2, 2)
        p1 = round(1.0 - p2, 2)
        
        current_scens = {
            'S1': {'prob': p1, 'attack': base_attack_s1},
            'S2': {'prob': p2, 'attack': base_attack_s2}
        }
        
        # 計算 EV 指標
        res = calculate_ev_metrics(f"Prob_{p2}", current_scens)
        
        if res:
            # 重新取得詳細決策
            solve_res = solve_robust_model(f"Prob_{p2}", current_scenarios=current_scens)
            
            # 格式化決策字串 (排序以確保比對正確)
            raw_h = solve_res['Hardened']
            raw_g = solve_res['New DGs']
            current_h_str = str(sorted(raw_h))
            current_g_str = str(sorted(raw_g))
            
            current_decision_key = f"{current_h_str}|{current_g_str}"
            current_obj = res['Obj Value']
            
            # --- 智慧判斷邏輯 ---
            note = ""
            if last_decision_str is not None:
                # 1. 決策內容改變了嗎?
                if current_decision_key != last_decision_str:
                    # 2. 成本改變了嗎? (真正的翻轉)
                    if abs(current_obj - last_obj_val) > 1e-4:
                        note = "<--- ★ 決策翻轉"
                    else:
                        # 決策變了但成本沒變 -> 等價解
                        note = "(等價解 Alt. Opt.)"
            
            last_decision_str = current_decision_key
            last_obj_val = current_obj
            
            # 恢復輸出並印出表格行
            sys.stdout = original_stdout
            print(
                f"{p2:<8.1f} | "
                f"{res['Obj Value']:<9.1f} | "
                f"{res['VSS']:<9.1f} | "
                f"{str(raw_h):<12} | "      # 顯示強化線路
                f"{str(raw_g):<10} | "      # 顯示發電機
                f"{note}"
            )
            sys.stdout = open(os.devnull, 'w') 
            
            sensitivity_results.append({
                "S2_Prob": p2, 
                "VSS": res['VSS'], 
                "Invest_Cost": solve_res['Invest ($)'],
                "Hardened": str(raw_h), 
                "New_DGs": str(raw_g)
            })
    
    sys.stdout = original_stdout
    df_sen = pd.DataFrame(sensitivity_results)
    df_sen.to_csv("Sensitivity_Analysis_S2_Prob.csv", index=False)
    print("-" * 110)
    print("✅ 敏感度分析完成！(決策細節已列出)\n")
    return df_sen

# ==========================================
# 繪圖函式
# ==========================================
def plot_charts(df):
    # 1. VSS Curve 
    plt.figure(figsize=(12, 7))
    plt.plot(df['S2_Prob'], df['VSS'], marker='o', color='#2ca02c', label='VSS')
    plt.fill_between(df['S2_Prob'], df['VSS'], alpha=0.3, color='#98df8a')
    
    max_idx = df['VSS'].idxmax()
    max_vss = df.loc[max_idx, 'VSS']
    max_prob = df.loc[max_idx, 'S2_Prob']
    
    plt.plot(max_prob, max_vss, marker='*', color='red', markersize=18, linestyle='None', label='Peak Value')
    
    offset_x = -0.2 if max_prob > 0.6 else 0.15
    plt.annotate(f'Peak Value\n${max_vss:,.0f}\n(Prob={max_prob:.1f})', 
                 xy=(max_prob, max_vss), xytext=(max_prob + offset_x, max_vss),
                 arrowprops=dict(facecolor='black', shrink=0.05, width=1),
                 horizontalalignment='center', fontsize=12, fontweight='bold',
                 bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.9))

    plt.title('Value of Robust Planning (VSS Curve)', fontsize=18, fontweight='bold', y=1.02)
    plt.xlabel('Probability of Scenario 2', fontsize=14); plt.ylabel('Cost Saving ($)', fontsize=14)
    plt.xticks(np.arange(0, 1.1, 0.1)); plt.legend(fontsize=12, loc='upper right')
    plt.grid(True, linestyle='--', alpha=0.7); plt.tight_layout()
    plt.show()

    # 2. Investment Steps 
    plt.figure(figsize=(12, 7))
    plt.step(df['S2_Prob'], df['Invest_Cost'], where='post', linewidth=3, color='#1f77b4', label='Investment Cost')
    
    last_decision_str = None
    
    # 用來錯開文字高度，避免重疊
    toggle_height = 0 
    
    for i, row in df.iterrows():
        # 組合決策字串
        h_clean = row['Hardened'].replace("[","").replace("]","").replace("'","")
        g_clean = row['New_DGs'].replace("[","").replace("]","").replace("'","")
        current_decision_str = f"{h_clean}|{g_clean}"
        
        # 判斷：成本變了 OR 內容變了，都要標示
        if current_decision_str != last_decision_str:
            txt = f"${row['Invest_Cost']:.0f}\nH:[{h_clean}]\nG:[{g_clean}]"
            
            # 畫點
            plt.plot(row['S2_Prob'], row['Invest_Cost'], 'o', color='orange', markersize=8, zorder=5)
            
            # 畫文字 (上下錯開)
            y_offset = 25 if toggle_height % 2 == 0 else 65
            toggle_height += 1
            
            plt.text(row['S2_Prob'], row['Invest_Cost'] + y_offset, txt, 
                     fontsize=9, ha='left',
                     bbox=dict(fc='white', alpha=0.9, ec='gray', boxstyle='round,pad=0.3'))
            
            # 如果是內容變但成本沒變，畫一條虛線垂直線提醒
            if i > 0 and row['Invest_Cost'] == df.iloc[i-1]['Invest_Cost']:
                plt.vlines(row['S2_Prob'], 0, row['Invest_Cost'], colors='red', linestyles='dotted', alpha=0.5)

            last_decision_str = current_decision_str

    plt.title('Investment Strategy Tipping Points (Content Sensitive)', fontsize=16, fontweight='bold')
    plt.xlabel('Probability of Scenario 2', fontsize=14); plt.ylabel('Investment Cost ($)', fontsize=14)
    plt.xticks(np.arange(0, 1.1, 0.1)); plt.grid(True, linestyle='--', alpha=0.7)
    plt.ylim(bottom=0, top=df['Invest_Cost'].max()*1.5) # 加高上限以容納文字
    plt.tight_layout()
    plt.show()

# ==========================================
# 7. 主程式執行 
# ==========================================

# 1. 印出攻擊符號表
print_legend(attack_legend)

print("開始批次分析 6 種情境設定...\n")

# 2. 設定 Phase 4 表格標題
header = (
    f"{'Case Name':<11} | {'S1/S2(Code) Prob':<18} | {'Hardened':<10} | {'New DGs':<8} | "
    f"{'RP ($)':<9} | {'WS ($)':<9} | {'EEV ($)':<9} | {'EVPI ($)':<9} | {'VSS ($)':<9}"
)
print(header)
print("-" * 115) 

final_results = []

# 3. 執行 Phase 4 分析
for name, scens in test_cases:
    res = calculate_ev_metrics(name, scens)
    
    if res:
        s1_atk = tuple(sorted(scens['S1']['attack']))
        s2_atk = tuple(sorted(scens['S2']['attack']))
        code1 = attack_map.get(s1_atk, "?")
        code2 = attack_map.get(s2_atk, "?")
        
        prob_str = f"{res['S1 Prob']}({code1})/{res['S2 Prob']}({code2})"
        
        print(
            f"{res['Case Name']:<11} | "
            f"{prob_str:<18} | "
            f"{str(res['Hardened']):<10} | "
            f"{str(res['New DGs']):<8} | "
            f"{res['Obj Value']:<9.1f} | "
            f"{res['WS']:<9.1f} | "
            f"{res['EEV']:<9.1f} | "
            f"{res['EVPI']:<9.1f} | "
            f"{res['VSS']:<9.1f}"
        )
        
        final_results.append({
            "Case": res['Case Name'],
            "RP": res['Obj Value'], "WS": res['WS'], "EEV": res['EEV'], 
            "EVPI": res['EVPI'], "VSS": res['VSS'],
            "S1_Prob": res['S1 Prob'], "S1_Code": code1, 
            "S2_Prob": res['S2 Prob'], "S2_Code": code2,
            "Hardened": res['Hardened'], "New_DGs": res['New DGs']
        })

df = pd.DataFrame(final_results)
cols = ["Case", "RP", "WS", "EEV", "EVPI", "VSS", "S1_Prob", "S1_Code", "S2_Prob", "S2_Code", "Hardened", "New_DGs"]
df = df[cols]
df.to_csv("Robust_Analysis_Summary.csv", index=False)

# 4. 執行 Phase 5 敏感度分析 (含 Tipping Point 表格)
df_sensitivity = run_sensitivity_analysis()

# 5. 繪製圖表 
plot_charts(df_sensitivity)