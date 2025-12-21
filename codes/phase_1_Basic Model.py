# -*- coding: utf-8 -*-
import gurobipy as gp
from gurobipy import GRB
import networkx as nx
import matplotlib.pyplot as plt

# ==========================================
# 第一部分：參數定義 (Parameters)
# ==========================================

# 1. 基礎數據與單位轉換 (Unit Conversion)
# 這是為了解決物理計算上的數值問題，將單位標準化
S_base = 1000.0  # kVA (功率基準)
V_base = 4.16    # kV  (電壓基準)
Z_base = (V_base ** 2) * 1000 / S_base 
print(f"--- 系統參數 ---")
print(f"基準阻抗 Z_base = {Z_base:.4f} Ohms")

# 2. 節點與負載資料 (原始 kW -> p.u.)
# [cite_start]資料來源: zhang2020multi.pdf Fig. 6 [cite: 1684]
node_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
P_load_kW = {
    1: 0, 2: 66.67, 3: 85, 4: 100, 5: 56.67, 
    6: 76.67, 7: 56.67, 8: 100, 9: 142.67, 10: 0, 
    11: 133.33, 12: 281, 13: 56.67
}
# 轉換為 p.u.
P_load_pu = {i: val / S_base for i, val in P_load_kW.items()}
Q_load_pu = {i: 0 for i in node_ids} # 假設 Q=0

# 3. 線路資料 (拓撲結構)
# 根據修正後的 Fig. 6 判讀結果
lines_info = {
    1: (1, 2),   2: (2, 3),   3: (3, 4),   4: (2, 5),   5: (5, 6),
    6: (6, 7),   7: (7, 8),   8: (3, 8),   9: (8, 9),   10: (4, 9),
    11: (2, 10), 12: (10, 11), 13: (11, 12), 14: (12, 13), 15: (3, 13)
}
line_ids = list(lines_info.keys())

# 4. 電氣參數 (原始 Ohms -> p.u.)
# 假設值，因為論文未提供 R, X
R_raw = 0.1
X_raw = 0.1
R_pu = R_raw / Z_base
X_pu = X_raw / Z_base
Big_M = 10.0 # 用於鬆弛斷開線路的電壓限制

# ==========================================
# 第二部分：模型與變數定義 (Variables)
# ==========================================

model = gp.Model("DistFlow_Phase1")

# 1. 開關狀態 (v): Binary
# 對應論文: v_{ij}^{q,s} (Eq. 5h-3 之後的最終狀態變數) 
v = model.addVars(line_ids, vtype=GRB.BINARY, name="v")

# 2. 線路流動 (P, Q): Continuous
# 對應論文: P_{ij,t}^s, Q_{ij,t}^s (用於 Eq. 5b, 5c, 5d)
# 設定範圍 -10 到 10 p.u. (允許逆流)
P_flow = model.addVars(line_ids, lb=-10.0, ub=10.0, vtype=GRB.CONTINUOUS, name="P_flow")
Q_flow = model.addVars(line_ids, lb=-10.0, ub=10.0, vtype=GRB.CONTINUOUS, name="Q_flow")

# 3. 節點電壓平方 (U): Continuous
# 對應論文: U_{i,t}^s (Eq. 5g) [cite: 1408]
# 設定範圍 [(0.9)^2, (1.1)^2]
U = model.addVars(node_ids, lb=0.81, ub=1.21, vtype=GRB.CONTINUOUS, name="U")
U[1].lb = 1.0; U[1].ub = 1.0 # Slack Bus 固定

# 4. 負載削減量 (delta_P): Continuous
# 對應論文: \Delta P_{i,t}^s (Eq. 5e) 
delta_P = model.addVars(node_ids, lb=0, vtype=GRB.CONTINUOUS, name="delta_P")
delta_Q = model.addVars(node_ids, lb=0, vtype=GRB.CONTINUOUS, name="delta_Q")

for i in node_ids:
    delta_P[i].ub = P_load_pu[i] # 上限不能超過該點需求
    delta_Q[i].ub = Q_load_pu[i]

model.update()

# ==========================================
# 第三部分：限制式定義 (Constraints)
# ==========================================

# 1. 實功平衡 (Active Power Balance)
# 論文引用: Eq. (5b) 
# 公式: sum(P_in) - sum(P_out) = P_load - delta_P (在此簡化模型中無 P_gen)
for j in node_ids:
    if j == 1: continue # 跳過源頭 (Slack Bus)
    
    incoming = gp.quicksum(P_flow[l] for l, (u, v) in lines_info.items() if v == j)
    outgoing = gp.quicksum(P_flow[l] for l, (u, v) in lines_info.items() if u == j)
    
    model.addConstr(incoming - outgoing == (P_load_pu[j] - delta_P[j]), name=f"P_Bal_{j}")

# 2. 虛功平衡 (Reactive Power Balance)
# 論文引用: Eq. (5c)
# 公式: sum(Q_in) - sum(Q_out) = Q_load - delta_Q
for j in node_ids:
    if j == 1: continue
    
    incoming_Q = gp.quicksum(Q_flow[l] for l, (u, v) in lines_info.items() if v == j)
    outgoing_Q = gp.quicksum(Q_flow[l] for l, (u, v) in lines_info.items() if u == j)
    
    model.addConstr(incoming_Q - outgoing_Q == (Q_load_pu[j] - delta_Q[j]), name=f"Q_Bal_{j}")

# 3. 線路容量與開關邏輯
# 論文引用: Eq. (5d) [cite_start][cite: 1404]
# 公式: -P_max * v <= P <= P_max * v
for l in line_ids:
    model.addConstr(P_flow[l] <= 10.0 * v[l], name=f"P_Cap_Ub_{l}")
    model.addConstr(P_flow[l] >= -10.0 * v[l], name=f"P_Cap_Lb_{l}")
    model.addConstr(Q_flow[l] <= 10.0 * v[l], name=f"Q_Cap_Ub_{l}")
    model.addConstr(Q_flow[l] >= -10.0 * v[l], name=f"Q_Cap_Lb_{l}")

# 4. 電壓降方程式 (Voltage Drop with Big-M)
# 論文引用: Eq. (5c) [cite_start]與 (5d) 之間的 DistFlow 區塊 
# 說明: 這是線性化 DistFlow 的核心物理限制，配合 Big-M 處理開關狀態
# 公式: U_i - U_j - 2(R*P + X*Q) <= M(1-v)
for l, (i, j) in lines_info.items():
    lhs = U[i] - U[j] - 2 * (R_pu * P_flow[l] + X_pu * Q_flow[l])
    
    model.addConstr(lhs <= Big_M * (1 - v[l]), name=f"V_Drop_Ub_{l}")
    model.addConstr(lhs >= -Big_M * (1 - v[l]), name=f"V_Drop_Lb_{l}")

# 5. 輻射狀/防迴路限制 (Loop Prevention) 
# 論文引用: Eq. (5i)
# 基於圖論，無迴路圖的邊數 <= 節點數 - 1
# 公式: sum(v) <= N_bus - N_root 允許在全黑時斷開所有線路
# 這裡假設只有一個主網 (N_root=1)，即樹狀結構
# sum(v) <= N_bus - 1
model.addConstr(gp.quicksum(v[l] for l in line_ids) <= len(node_ids) - 1, name="Tree_Topo No_Loops")
#model.addConstr(gp.quicksum(v[l] for l in line_ids) == len(node_ids) - 1, name="Radial_Topo")
# ==========================================
# 第四部分：目標函式與求解
# ==========================================

# 目標: 最小化總實功負載削減
# 論文引用: Eq. (5a) 
# 公式: min sum(delta_P)

# 1. 主要目標：最小化停電 (權重最大，例如 1.0)
obj_shedding = gp.quicksum(delta_P[i] for i in node_ids)

# 2. 次要目標：最小化線路損耗 (權重很小，例如 1e-4)
# 用於消除幽靈流 (Ghost Flows)
# 近似: 因為 P^2 是二次式，這裡用簡單的線性流量總和做懲罰(絕對值)或直接用 P^2 (MIQP)
# 為保持線性模型簡單，我們這裡只用開關懲罰通常就夠了，但若要精確消除 P，可加 P_flow 平方
# 這裡 "開關懲罰" 就足以解決 Status 問題

# 3. 開關操作懲罰 (Operation Cost) (權重小，例如 0.01)
# 用於消除不必要的 ON 狀態，確保沒電的地方開關就是 OFF
obj_switching = 0.01 * gp.quicksum(v[l] for l in line_ids)

# 結合目標
model.setObjective(obj_shedding + obj_switching, GRB.MINIMIZE)
#model.setObjective(obj_shedding , GRB.MINIMIZE)

# --- 模擬災難 (Simulate Disaster) ---
#print("\n--- 模擬災難: 強制斷開 Line 2 和 Line 7 ---")
#v[2].ub = 0 
#v[7].ub = 0 

print("\n--- 模擬災難: Line 1 斷線 (全黑啟動測試) ---")
#v[1].ub = 0

#print("\n--- 模擬災難: Line 11 斷線  ---")
#v[11].ub = 0  

#print("\n--- 模擬災難: Line 1 和 Line 5 斷線  ---")
v[11].ub = 0 
v[5].ub = 0 

#print("\n--- 模擬災難: Line 2 和 Line 11 和15 斷線  ---")
#v[2].ub = 0 
#v[11].ub = 0 
#v[15].ub = 0 

model.optimize()

# ==========================================
# 第五部分：文字與圖形輸出
# ==========================================

if model.status == GRB.OPTIMAL:
    print(f"\n求解成功！最小總停電損失: {model.objVal * S_base:.4f} kW")

    # 1. 建立圖形
    G = nx.DiGraph()
    pos = {
        1: (0, 1),  2: (1, 1),  3: (3, 1),  4: (4, 1),
        5: (1, 0),  6: (2, 0),  7: (3, 0),  8: (3, 0.5), 9: (4, 0),
        10: (1, 2), 11: (2, 2), 12: (3, 2), 13: (3, 1.5)
    }
    for n in node_ids: G.add_node(n)

    # 2. 準備繪圖清單
    edges_on_visual = []
    edges_off_visual = []

    for l in line_ids:
        u, v_node = lines_info[l]
        flow = P_flow[l].x * S_base # kW
        
        if v[l].x > 0.5:
            # 標籤顯示: L{id}: {流量}
            label_text = f"L{l}: {abs(flow):.0f}"
            if flow >= 0:
                G.add_edge(u, v_node, weight=flow, label=label_text)
                edges_on_visual.append((u, v_node))
            else:
                G.add_edge(v_node, u, weight=abs(flow), label=label_text)
                edges_on_visual.append((v_node, u))
        else:
            G.add_edge(u, v_node, label=f"L{l}")
            edges_off_visual.append((u, v_node))

    # 3. 開始繪圖 
    plt.figure(figsize=(18, 12)) 
    
    # (A) 畫節點 & 標籤
    node_labels = {i: f"{i}\n{P_load_kW[i]:.0f}kW" for i in node_ids}
    nx.draw_networkx_nodes(G, pos, node_size=3500, node_color='#87CEFA', edgecolors='black')
    nx.draw_networkx_labels(G, pos, labels=node_labels, font_weight='bold', font_size=14)

    # (B) 畫線路 (加粗!)
    # ON = 綠色, 寬度 5
    nx.draw_networkx_edges(G, pos, edgelist=edges_on_visual, 
                           edge_color='green', width=5, arrows=True, arrowsize=50)
    # OFF = 紅色虛線, 寬度 5
    nx.draw_networkx_edges(G, pos, edgelist=edges_off_visual, 
                           edge_color='red', width=5, style='dashed', arrows=False, alpha=0.6)

    # (C) 畫線路標籤
    edge_labels = nx.get_edge_attributes(G, 'label')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, 
                                 font_color='darkblue', 
                                 font_size=16, # 線路文字大小
                                 font_weight='bold',
                                 bbox=dict(facecolor='white', edgecolor='none', alpha=0.9, boxstyle='round,pad=0.2'))

    # (D) 標題與圖例
    #plt.title(f"Phase 1 Result (L2 & L7 Broken)\nTotal Load Shedding: {model.objVal * S_base:.2f} kW", fontsize=24)
    plt.title(f"Phase 1 Result (L1 Broken)\nTotal Load Shedding: {model.objVal * S_base:.2f} kW", fontsize=24)
    #plt.title(f"Phase 1 Result (L11 Broken)\nTotal Load Shedding: {model.objVal * S_base:.2f} kW", fontsize=24)
    #plt.title(f"Phase 1 Result (L, L11 & L15 Broken)\nTotal Load Shedding: {model.objVal * S_base:.2f} kW", fontsize=24)
    
    # 圖例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#87CEFA', markersize=18, markeredgecolor='black', label='Node (Load kW)'),
        Line2D([0], [0], color='green', lw=5, label='Active Line'),
        Line2D([0], [0], color='red', lw=5, linestyle='--', label='Broken/Open Line')
    ]
    plt.legend(handles=legend_elements, loc='upper left', fontsize=16)
    
    plt.axis('off')
    plt.tight_layout()
    plt.show()

    # --- 文字報告  ---
    print("\n" + "="*40)
    print(f"  PHASE 1 最佳化結果報告")
    print("="*40)
    print(f"最小總停電損失 (Total Load Shedding): {model.objVal * S_base:.4f} kW")
    
    print("\n[線路狀態報告]")
    print(f"{'Line':<5} {'From-To':<10} {'Status':<8} {'Flow (kW)':<10}")
    print("-" * 35)
    for l in line_ids:
        p_kw = P_flow[l].x * S_base
        status = "ON" if v[l].x > 0.5 else "OFF"
        flow_str = f"{p_kw:.2f}" if status == "ON" else "0.00"
        print(f"L{l:<4} {lines_info[l][0]:<2}->{lines_info[l][1]:<2}    {status:<8} {flow_str:<10}")
            
else:
    print("求解失敗或無可行解。")
    model.computeIIS()
    model.write("model.ilp")