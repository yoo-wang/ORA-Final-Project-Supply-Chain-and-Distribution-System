# -*- coding: utf-8 -*-
import gurobipy as gp
from gurobipy import GRB
import networkx as nx
import matplotlib.pyplot as plt

# ==========================================
# 第一部分：參數定義 (Parameters)
# ==========================================

# 1. 基礎系統參數
S_base = 1000.0  # kVA
V_base = 4.16    # kV
Z_base = (V_base ** 2) * 1000 / S_base 
print(f"--- 系統參數 ---")
print(f"基準阻抗 Z_base = {Z_base:.4f} Ohms")

# 2. 節點與負載
node_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
P_load_kW = {
    1: 0, 2: 66.67, 3: 85, 4: 100, 5: 56.67, 
    6: 76.67, 7: 56.67, 8: 100, 9: 142.67, 10: 0, 
    11: 133.33, 12: 281, 13: 56.67
}
P_load_pu = {i: val / S_base for i, val in P_load_kW.items()}
Q_load_pu = {i: 0 for i in node_ids} 

# 3. 線路資料
lines_info = {
    1: (1, 2),   2: (2, 3),   3: (3, 4),   4: (2, 5),   5: (5, 6),
    6: (6, 7),   7: (7, 8),   8: (3, 8),   9: (8, 9),   10: (4, 9),
    11: (2, 10), 12: (10, 11), 13: (11, 12), 14: (12, 13), 15: (3, 13)
}
line_ids = list(lines_info.keys())

# 4. 電氣參數
R_pu = 0.1 / Z_base; X_pu = 0.1 / Z_base; Big_M = 10.0 

# 5. 投資成本與預算 
Cost_DG_kW = 1.5; Cost_Hard_Line = 400.0; Cost_Shedding = 14.0
Budget_H = 1; Budget_G = 1
DG_Cap_kW = 100.0; DG_Cap_pu = DG_Cap_kW / S_base

# --- [Phase 3] 災害情境定義  ---
"""
Scenarios = {
    'S1': {'prob': 0.1, 'attack': [2, 11], 'desc': 'S1 (Freq, K=2) - Attack L2, L11'},
    'S2': {'prob': 0.9, 'attack': [2,  5, 8, 14, 15], 'desc': 'S2 (Rare, K=5) - Attack L2,5,8,14,15'}
}

"""
Scenarios = {
    'S1': {'prob': 0.1, 'attack': [4, 6, 11], 'desc': 'S1 (Freq, K=3) - Attack L4, L6, L11'},
    'S2': {'prob': 0.9, 'attack': [2, 5, 8, 14, 15], 'desc': 'S2 (Rare, K=5) - Attack L2,5,8,14,15'}
}



scenario_keys = list(Scenarios.keys())

# ==========================================
# 第二部分：模型與變數定義
# ==========================================

model = gp.Model("DistFlow_Phase3_Robust")

# --- 1. 第一階段變數 (投資決策 - 全域唯一) ---
y_h = model.addVars(line_ids, vtype=GRB.BINARY, name="y_h") 
candidate_nodes = [i for i in node_ids if i != 1]
y_g = model.addVars(candidate_nodes, vtype=GRB.BINARY, name="y_g") 

# --- 2. 第二階段變數 (營運操作 - 針對每個情境複製一份) ---
v = model.addVars(line_ids, scenario_keys, vtype=GRB.BINARY, name="v")
P_flow = model.addVars(line_ids, scenario_keys, lb=-10, ub=10, vtype=GRB.CONTINUOUS, name="P")
Q_flow = model.addVars(line_ids, scenario_keys, lb=-10, ub=10, vtype=GRB.CONTINUOUS, name="Q")
U = model.addVars(node_ids, scenario_keys, lb=0.81, ub=1.21, vtype=GRB.CONTINUOUS, name="U")
delta_P = model.addVars(node_ids, scenario_keys, lb=0, vtype=GRB.CONTINUOUS, name="dP")
delta_Q = model.addVars(node_ids, scenario_keys, lb=0, vtype=GRB.CONTINUOUS, name="dQ")
P_gen = model.addVars(candidate_nodes, scenario_keys, lb=0, ub=DG_Cap_pu, vtype=GRB.CONTINUOUS, name="Pgen")

for s in scenario_keys:
    U[1, s].lb = 1.0; U[1, s].ub = 1.0 
    for i in node_ids:
        delta_P[i, s].ub = P_load_pu[i]
        delta_Q[i, s].ub = Q_load_pu[i]

model.update()

# ==========================================
# 第三部分：限制式定義
# ==========================================

# --- 1. 預算限制 ---
model.addConstr(gp.quicksum(y_h[l] for l in line_ids) <= Budget_H, name="Budget_H")
model.addConstr(gp.quicksum(y_g[i] for i in candidate_nodes) <= Budget_G, name="Budget_G")

# --- 2. 情境迴圈 ---
for s in scenario_keys:
    attack_set = Scenarios[s]['attack']
    
    # (A) 連結限制：存活邏輯
    for l in line_ids:
        if l in attack_set:
            model.addConstr(v[l, s] <= y_h[l], name=f"Survive_{l}_{s}")
            
    # (B) 連結限制：發電機邏輯
    for i in candidate_nodes:
        model.addConstr(P_gen[i, s] <= DG_Cap_pu * y_g[i], name=f"DG_Logic_{i}_{s}")

    # (C) 物理限制 (DistFlow)
    for j in node_ids:
        if j == 1: continue
        # 實功平衡
        inc = gp.quicksum(P_flow[l, s] for l, (u, v_n) in lines_info.items() if v_n == j)
        out = gp.quicksum(P_flow[l, s] for l, (u, v_n) in lines_info.items() if u == j)
        gen = P_gen[j, s] if j in candidate_nodes else 0
        model.addConstr(inc - out + gen == P_load_pu[j] - delta_P[j, s], name=f"P_Bal_{j}_{s}")
        
        # 虛功平衡
        inc_q = gp.quicksum(Q_flow[l, s] for l, (u, v_n) in lines_info.items() if v_n == j)
        out_q = gp.quicksum(Q_flow[l, s] for l, (u, v_n) in lines_info.items() if u == j)
        model.addConstr(inc_q - out_q == Q_load_pu[j] - delta_Q[j, s], name=f"Q_Bal_{j}_{s}")

    # 線路容量與電壓降
    for l in line_ids:
        model.addConstr(P_flow[l, s] <= 10*v[l, s]); model.addConstr(P_flow[l, s] >= -10*v[l, s])
        model.addConstr(Q_flow[l, s] <= 10*v[l, s]); model.addConstr(Q_flow[l, s] >= -10*v[l, s])
        
        u, v_n = lines_info[l]
        lhs = U[u, s] - U[v_n, s] - 2*(R_pu*P_flow[l, s] + X_pu*Q_flow[l, s])
        model.addConstr(lhs <= Big_M*(1-v[l, s]))
        model.addConstr(lhs >= -Big_M*(1-v[l, s]))

    # 防迴路限制
    model.addConstr(gp.quicksum(v[l, s] for l in line_ids) <= len(node_ids) - 1, name=f"NoLoop_{s}")

# ==========================================
# 第四部分：目標函式
# ==========================================

cost_inv = Cost_Hard_Line * gp.quicksum(y_h[l] for l in line_ids) + \
           (Cost_DG_kW * DG_Cap_kW) * gp.quicksum(y_g[i] for i in candidate_nodes)

expected_shedding_cost = 0
for s in scenario_keys:
    prob = Scenarios[s]['prob']
    loss_s = Cost_Shedding * gp.quicksum(delta_P[i, s] for i in node_ids) * S_base
    switching_s = 0.01 * gp.quicksum(v[l, s] for l in line_ids) 
    expected_shedding_cost += prob * (loss_s + switching_s)

model.setObjective(cost_inv + expected_shedding_cost, GRB.MINIMIZE)

print("\n--- 開始求解 Phase 3 Robust Planning (Path B) ---")
model.optimize()

# ==========================================
# 第五部分：結果輸出 
# ==========================================

def plot_scenario_stage2_style(s_key):
    """ 使用與 Phase 2 完全相同的樣式繪製 """
    print(f"\n--- 繪製情境 {s_key} 結果 ---")
    G = nx.DiGraph()
    pos = {1:(0,1), 2:(1,1), 3:(3,1), 4:(4,1), 5:(1,0), 6:(2,0), 7:(3,0), 
           8:(3,0.5), 9:(4,0), 10:(1,2), 11:(2,2), 12:(3,2), 13:(3,1.5)}
    for n in node_ids: G.add_node(n)
    
    edges_on = []
    edges_hardened = [] 
    edges_off_normal = []
    edges_off_attacked = [] 
    
    attack_set = Scenarios[s_key]['attack']

    for l in line_ids:
        u, v_node = lines_info[l]
        flow = P_flow[l, s_key].x * S_base
        is_on = v[l, s_key].x > 0.5
        is_hardened = y_h[l].x > 0.5
        is_attacked = l in attack_set
        
        if is_on: # ON
            label_text = f"L{l}: {abs(flow):.0f}"
            if flow >= 0:
                G.add_edge(u, v_node, weight=flow, label=label_text)
                edges_on.append((u, v_node))
            else:
                G.add_edge(v_node, u, weight=abs(flow), label=label_text)
                edges_on.append((v_node, u))
            
            if is_hardened:
                edges_hardened.append((u, v_node) if flow >= 0 else (v_node, u))
                
        else: # OFF
            label_text = f"L{l}"
            if is_attacked:
                label_text += " (Attacked!)"
                edges_off_attacked.append((u, v_node))
            else:
                edges_off_normal.append((u, v_node))
            G.add_edge(u, v_node, label=label_text)

    # 繪圖
    plt.figure(figsize=(18, 12)) 
    
    colors = []
    for i in node_ids:
        if i in candidate_nodes and y_g[i].x > 0.5:
            colors.append('#FFD700') 
        elif delta_P[i, s_key].x * S_base > 1e-3: 
            colors.append('#FF6347') 
        else:
            colors.append('#87CEFA') 
            
    node_labels = {i: f"{i}\n{P_load_kW[i]:.0f}kW" for i in node_ids}
    nx.draw_networkx_nodes(G, pos, node_size=3500, node_color=colors, edgecolors='black')
    nx.draw_networkx_labels(G, pos, labels=node_labels, font_weight='bold', font_size=14)

    nx.draw_networkx_edges(G, pos, edgelist=edges_on, edge_color='green', width=5, arrows=True, arrowsize=50)
    nx.draw_networkx_edges(G, pos, edgelist=edges_hardened, edge_color='blue', width=7, arrows=True, arrowsize=50, alpha=0.6)
    nx.draw_networkx_edges(G, pos, edgelist=edges_off_normal, edge_color='gray', width=3, style='dashed', arrows=False, alpha=0.5)
    nx.draw_networkx_edges(G, pos, edgelist=edges_off_attacked, edge_color='red', width=6, style='dotted', arrows=False)

    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='darkblue', font_size=12, font_weight='bold', bbox=dict(facecolor='white', edgecolor='none', alpha=0.9))

    loss_val = sum(delta_P[i, s_key].x for i in node_ids) * S_base * Cost_Shedding
    plt.title(f"Phase 3 Result [{s_key}]: {Scenarios[s_key]['desc']}\nLoss: ${loss_val:,.0f} (Red Nodes = Shedding)", fontsize=24)
    
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#FFD700', markersize=18, label='Node with New DG'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#FF6347', markersize=18, label='Node Shedding'),
        Line2D([0], [0], color='blue', lw=5, label='Hardened Line (Saved)'),
        Line2D([0], [0], color='red', lw=5, linestyle=':', label='Attacked & Broken')
    ]
    plt.legend(handles=legend_elements, loc='upper left', fontsize=16)
    plt.axis('off'); plt.tight_layout(); plt.show()

# --- 主程式輸出邏輯  ---
if model.status == GRB.OPTIMAL:
    print("\n" + "="*60)
    print(f"  Phase 3: Path B Robust Planning Result")
    print("="*60)
    
    # 1. 投資決策
    print(f"\n[最佳投資方案] (總投資成本: ${cost_inv.getValue():,.0f})")
    print("🛡️  強化線路:", end=" ")
    hardened_lines = [l for l in line_ids if y_h[l].x > 0.5]
    print(hardened_lines if hardened_lines else "無")
    
    print("🔋 新增發電機:", end=" ")
    new_dgs = [i for i in candidate_nodes if y_g[i].x > 0.5]
    print(new_dgs if new_dgs else "無")
    
    print("-" * 60)
    
    # 2. 各情境詳細表現 + 停電原因分析
    print(f"[各情境表現]")
    for s in scenario_keys:
        prob = Scenarios[s]['prob']
        desc = Scenarios[s]['desc']
        shed_kw = sum(delta_P[i, s].x for i in node_ids) * S_base
        loss_cost = shed_kw * Cost_Shedding
        
        # 判斷實際斷線
        actual_broken = []
        for l in line_ids:
            if l in Scenarios[s]['attack']:
                if y_h[l].x < 0.5: # 沒強化
                    actual_broken.append(l)
        
        print(f"\n>> 情境 {s} ({desc}):")
        print(f"   - 機率: {prob*100:.1f}%")
        print(f"   - 實際斷線: Line {actual_broken}")
        print(f"   - 總停電損失: ${loss_cost:,.0f} ({shed_kw:.2f} kW)")
        
        # --- [NEW] 詳細停電原因分析 ---
        any_local_shedding = False
        for i in node_ids:
            node_shed_kw = delta_P[i, s].x * S_base
            if node_shed_kw > 1e-3: # 有停電
                any_local_shedding = True
                local_loss = node_shed_kw * Cost_Shedding
                dg_cost = Cost_DG_kW * DG_Cap_kW
                
                print(f"     ⚠️ Node {i} 停電 {node_shed_kw:.2f} kW (損失 ${local_loss:,.0f})")
                
                # 原因分析
                if local_loss < dg_cost:
                    print(f"        -> 原因: 不划算 (損失 < 發電成本)，且未受惠於投資方案。")
                elif y_g[i].x < 0.5:
                    print(f"        -> 原因: 預算限制 ($G=1)，發電機蓋在別處效益更高。")
                else:
                    print(f"        -> 原因: 即使有發電機，仍無法滿足全部負載 (容量不足或孤島)。")
        
        if not any_local_shedding:
            print("     ✅ 供電完全正常。")

    print("\n" + "-" * 60)
    print(f"總加權預期成本 (Objective): ${model.objVal:,.2f}")

    # 3. 繪圖
    plot_scenario_stage2_style('S1')
    plot_scenario_stage2_style('S2')

else:
    print("求解失敗。")
    model.computeIIS()
    model.write("model.ilp")