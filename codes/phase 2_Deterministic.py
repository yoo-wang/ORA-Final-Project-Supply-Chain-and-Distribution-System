# -*- coding: utf-8 -*-
import gurobipy as gp
from gurobipy import GRB
import networkx as nx
import matplotlib.pyplot as plt

# ==========================================
# 第一部分：參數定義 (Parameters)
# ==========================================

# 1. 基礎數據與單位轉換
S_base = 1000.0  # kVA
V_base = 4.16    # kV
Z_base = (V_base ** 2) * 1000 / S_base 
print(f"--- 系統參數 ---")
print(f"基準阻抗 Z_base = {Z_base:.4f} Ohms")

# 2. 節點與負載資料
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
R_pu = 0.1 / Z_base
X_pu = 0.1 / Z_base
Big_M = 10.0 

# --- [Phsae 2] 投資成本與預算 ---
Cost_DG_kW = 1.5      # 發電機 ($/kW)
Cost_Hard_Line = 400.0   # 強化 ($/Line)
Cost_Shedding = 14.0     # 停電懲罰 ($/kW)

Budget_H = 1             # 預算: 最多強化 1 條 
Budget_G = 1             # 預算: 最多蓋 1 台
DG_Cap_kW = 100.0        # 發電機容量 (kW)
DG_Cap_pu = DG_Cap_kW / S_base

# ==========================================
# 第二部分：模型與變數定義 (Variables)
# ==========================================

model = gp.Model("DistFlow_Phsae2_Planning")

# 1. 物理變數
v = model.addVars(line_ids, vtype=GRB.BINARY, name="v")
P_flow = model.addVars(line_ids, lb=-10.0, ub=10.0, vtype=GRB.CONTINUOUS, name="P_flow")
Q_flow = model.addVars(line_ids, lb=-10.0, ub=10.0, vtype=GRB.CONTINUOUS, name="Q_flow")
U = model.addVars(node_ids, lb=0.81, ub=1.21, vtype=GRB.CONTINUOUS, name="U")
U[1].lb = 1.0; U[1].ub = 1.0 
delta_P = model.addVars(node_ids, lb=0, vtype=GRB.CONTINUOUS, name="delta_P")
delta_Q = model.addVars(node_ids, lb=0, vtype=GRB.CONTINUOUS, name="delta_Q")

for i in node_ids:
    delta_P[i].ub = P_load_pu[i] 
    delta_Q[i].ub = Q_load_pu[i]

# 2. 投資決策變數
y_h = model.addVars(line_ids, vtype=GRB.BINARY, name="y_h")
candidate_nodes = [i for i in node_ids if i != 1]
y_g = model.addVars(candidate_nodes, vtype=GRB.BINARY, name="y_g")
P_gen = model.addVars(candidate_nodes, lb=0, ub=DG_Cap_pu, vtype=GRB.CONTINUOUS, name="P_gen")

model.update()

# ==========================================
# 第三部分：限制式定義 (Constraints)
# ==========================================

# 1. 預算限制
model.addConstr(gp.quicksum(y_h[l] for l in line_ids) <= Budget_H, name="Budget_H")
model.addConstr(gp.quicksum(y_g[i] for i in candidate_nodes) <= Budget_G, name="Budget_G")

# 2. 發電機邏輯
for i in candidate_nodes:
    model.addConstr(P_gen[i] <= DG_Cap_pu * y_g[i], name=f"DG_Logic_{i}")

# 3. 實功平衡
for j in node_ids:
    if j == 1: continue
    incoming = gp.quicksum(P_flow[l] for l, (u, v) in lines_info.items() if v == j)
    outgoing = gp.quicksum(P_flow[l] for l, (u, v) in lines_info.items() if u == j)
    gen_p = P_gen[j] if j in candidate_nodes else 0
    model.addConstr(incoming - outgoing + gen_p == (P_load_pu[j] - delta_P[j]), name=f"P_Bal_{j}")

# 4. 虛功平衡
for j in node_ids:
    if j == 1: continue
    incoming_Q = gp.quicksum(Q_flow[l] for l, (u, v) in lines_info.items() if v == j)
    outgoing_Q = gp.quicksum(Q_flow[l] for l, (u, v) in lines_info.items() if u == j)
    model.addConstr(incoming_Q - outgoing_Q == (Q_load_pu[j] - delta_Q[j]), name=f"Q_Bal_{j}")

# 5. 線路容量
for l in line_ids:
    model.addConstr(P_flow[l] <= 10.0 * v[l])
    model.addConstr(P_flow[l] >= -10.0 * v[l])
    model.addConstr(Q_flow[l] <= 10.0 * v[l])
    model.addConstr(Q_flow[l] >= -10.0 * v[l])

# 6. 電壓降
for l, (i, j) in lines_info.items():
    lhs = U[i] - U[j] - 2 * (R_pu * P_flow[l] + X_pu * Q_flow[l])
    model.addConstr(lhs <= Big_M * (1 - v[l]))
    model.addConstr(lhs >= -Big_M * (1 - v[l]))

# 7. 防迴路限制
model.addConstr(gp.quicksum(v[l] for l in line_ids) <= len(node_ids) - 1, name="No_Loops")

# --- 災難與防禦邏輯 ---
#attacked_lines = [2, 6, 11, 15] # 可以在這裡自由修改
#attacked_lines = [2, 4, 6, 11] # 可以在這裡自由修改
#attacked_lines = [2, 6, 9, 11, 15] 
#attacked_lines = [4, 7] 
print(f"\n--- 設定災難情境: 攻擊 Line {attacked_lines} ---")

for l in attacked_lines:
    model.addConstr(v[l] <= y_h[l], name=f"Survival_{l}")

# ==========================================
# 第四部分：目標函式與求解
# ==========================================

# 1. 投資成本
cost_inv_hardening = Cost_Hard_Line * gp.quicksum(y_h[l] for l in line_ids)
cost_inv_dg = (Cost_DG_kW * DG_Cap_kW) * gp.quicksum(y_g[i] for i in candidate_nodes)

# 2. 營運成本
cost_shedding = Cost_Shedding * gp.quicksum(delta_P[i] for i in node_ids) * S_base

# 3. 開關懲罰
cost_switching = 0.01 * gp.quicksum(v[l] for l in line_ids)

model.setObjective(cost_inv_hardening + cost_inv_dg + cost_shedding + cost_switching, GRB.MINIMIZE)

model.optimize()

# ==========================================
# 第五部分：結果輸出與繪圖
# ==========================================

if model.status == GRB.OPTIMAL:
    # --- 文字報告 ---
    print("\n" + "="*50)
    print(f"  PHASE 2 最佳化規劃結果 (Defender)")
    print("="*50)
    print(f"總成本 (Total Cost):   ${model.objVal:,.2f}")
    print(f"  - 強化投資:        ${cost_inv_hardening.getValue():,.2f}")
    print(f"  - 發電投資:        ${cost_inv_dg.getValue():,.2f}")
    print(f"  - 停電損失:        ${cost_shedding.getValue():,.2f}")
    print("-" * 50)
    
    print("\n[決策結果]")
    print("🛡️  強化線路 (Hardened Lines):")
    any_hardening = False
    for l in line_ids:
        if y_h[l].x > 0.5:
            print(f"   - Line {l} (Cost: ${Cost_Hard_Line})")
            any_hardening = True
    if not any_hardening: print("   (無)")
            
    print("🔋 新增發電機 (New B-DGs):")
    any_dg = False
    for i in candidate_nodes:
        if y_g[i].x > 0.5:
            print(f"   - Node {i} (Cost: ${Cost_DG_kW * DG_Cap_kW:,.0f}, Output: {P_gen[i].x * S_base:.2f} kW)")
            any_dg = True
    if not any_dg: print("   (無)")

    # --- [NEW] 停電原因分析 (修正版) ---
    print("\n[停電原因分析]")
    any_shedding = False
    for i in node_ids:
        shed_kw = delta_P[i].x * S_base
        if shed_kw > 1e-3: # 降低閾值，確保捕捉微小停電
            any_shedding = True
            loss_cost = shed_kw * Cost_Shedding
            dg_cost = Cost_DG_kW * DG_Cap_kW
            print(f"⚠️ Node {i} 停電 {shed_kw:.2f} kW (損失 ${loss_cost:,.0f})")
            if loss_cost < dg_cost:
                print(f"   -> 原因: 停電損失 (${loss_cost:,.0f}) < 發電機成本 (${dg_cost:,.0f})，所以不蓋發電機。")
            else:
                print(f"   -> 原因: 可能是預算不足或無其他救援路徑。")
    
    if not any_shedding:
        print("✅ 恭喜！全系統供電正常，無任何停電損失。")

    # --- 繪圖部分 (增強標示 + 動態標題) ---
    G = nx.DiGraph()
    pos = {
        1: (0, 1),  2: (1, 1),  3: (3, 1),  4: (4, 1),
        5: (1, 0),  6: (2, 0),  7: (3, 0),  8: (3, 0.5), 9: (4, 0),
        10: (1, 2), 11: (2, 2), 12: (3, 2), 13: (3, 1.5)
    }
    for n in node_ids: G.add_node(n)

    edges_on = []
    edges_hardened = [] 
    edges_off_normal = []
    edges_off_attacked = [] 

    for l in line_ids:
        u, v_node = lines_info[l]
        flow = P_flow[l].x * S_base
        
        if v[l].x > 0.5: # ON
            label_text = f"L{l}: {abs(flow):.0f}"
            if flow >= 0:
                G.add_edge(u, v_node, weight=flow, label=label_text)
                edges_on.append((u, v_node))
            else:
                G.add_edge(v_node, u, weight=abs(flow), label=label_text)
                edges_on.append((v_node, u))
            
            if y_h[l].x > 0.5:
                edges_hardened.append((u, v_node) if flow >= 0 else (v_node, u))
                
        else: # OFF
            label_text = f"L{l}"
            # 判斷是否為被攻擊的線路
            if l in attacked_lines:
                label_text += " (Attacked!)"
                edges_off_attacked.append((u, v_node))
            else:
                edges_off_normal.append((u, v_node))
            
            G.add_edge(u, v_node, label=label_text)

    plt.figure(figsize=(18, 12)) 
    
    # 畫節點
    colors = []
    for i in node_ids:
        if i in candidate_nodes and y_g[i].x > 0.5:
            colors.append('#FFD700') 
        elif delta_P[i].x * S_base > 1e-3: # 使用相同閾值
            colors.append('#FF6347')
        else:
            colors.append('#87CEFA') 
            
    node_labels = {i: f"{i}\n{P_load_kW[i]:.0f}kW" for i in node_ids}
    nx.draw_networkx_nodes(G, pos, node_size=3500, node_color=colors, edgecolors='black')
    nx.draw_networkx_labels(G, pos, labels=node_labels, font_weight='bold', font_size=14)

    # 畫線路
    nx.draw_networkx_edges(G, pos, edgelist=edges_on, edge_color='green', width=5, arrows=True, arrowsize=50)
    nx.draw_networkx_edges(G, pos, edgelist=edges_hardened, edge_color='blue', width=7, arrows=True, arrowsize=50, alpha=0.6)
    nx.draw_networkx_edges(G, pos, edgelist=edges_off_normal, edge_color='gray', width=3, style='dashed', arrows=False, alpha=0.5)
    nx.draw_networkx_edges(G, pos, edgelist=edges_off_attacked, edge_color='red', width=6, style='dotted', arrows=False)

    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='darkblue', font_size=12, font_weight='bold', bbox=dict(facecolor='white', edgecolor='none', alpha=0.9))

    # [NEW] 動態標題: 顯示攻擊情境
    plt.title(f"Phase 2 Result: Lines {attacked_lines} Attacked\nTotal Cost: ${model.objVal:,.0f} (Red=Shedding, Gold=DG, Blue=Hardened)", fontsize=24)
    
    # 圖例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#FFD700', markersize=18, label='Node with New DG'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#FF6347', markersize=18, label='Node Shedding'),
        Line2D([0], [0], color='blue', lw=5, label='Hardened Line (Saved)'),
        Line2D([0], [0], color='red', lw=5, linestyle=':', label='Attacked & Broken')
    ]
    plt.legend(handles=legend_elements, loc='upper left', fontsize=16)
    
    plt.axis('off')
    plt.tight_layout()
    plt.show()

else:
    print("求解失敗或無可行解。")
    model.computeIIS()
    model.write("model.ilp")