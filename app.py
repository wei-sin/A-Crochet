import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import re
import matplotlib.pyplot as plt
import numpy as np
import math

# --- 初始化設定 ---

# 設定網頁基本資訊
st.set_page_config(page_title="AI-Crochet 創作紀錄", page_icon="🧶", layout="wide")

# 注入自訂 CSS 改變側邊欄顏色為 #A98B76 (奶茶/淺咖啡色)
st.markdown("""
    <style>
        [data-testid="stSidebar"] {
            background-color: #A98B76 !important;
        }
    </style>
""", unsafe_allow_html=True)

# 確保用來存放上傳圖片/檔案的資料夾存在
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# 資料庫連線與初始化函數
DB_FILE = 'crochet.db'

# 定義針法下拉選單選項
STITCH_OPTIONS = [
    "引拔SL", "鎖針CH",
    "短針X", "短加針V", "短減針A",
    "中長針T", "中長加針TV", "中長減針TA",
    "長針F", "長加針FV", "長減針FA"
]

# 定義計算總針數用的權重 (加針=2, 其他=1)
STITCH_WEIGHTS = {
    "SL": 1, "CH": 1,
    "X": 1, "V": 2, "A": 1,
    "T": 1, "TV": 2, "TA": 1,
    "F": 1, "FV": 2, "FA": 1
}

def parse_stitch_string(stitch_str):
    """解析表格字串 (如 '(X, V) * 6' 或 '6X')，轉為繪圖用的陣列"""
    flat_symbols = []
    stitch_str = str(stitch_str).strip()
    if not stitch_str or stitch_str.lower() in ["nan", "none"]: 
        return []

    repeat = 1
    pattern_str = stitch_str
    
    match_repeat = re.search(r'\((.*?)\)\s*[\*xX]\s*(\d+)', stitch_str)
    if match_repeat:
        pattern_str = match_repeat.group(1)
        repeat = int(match_repeat.group(2))
    else:
        match_repeat_no_paren = re.search(r'(.*?)\s*[\*xX]\s*(\d+)$', stitch_str)
        if match_repeat_no_paren:
            pattern_str = match_repeat_no_paren.group(1)
            repeat = int(match_repeat_no_paren.group(2))

    items = [x.strip() for x in pattern_str.split(',')]
    seq = []
    for item in items:
        if not item: continue
        match = re.match(r'^(\d+)?([A-Za-z]+)$', item)
        if match:
            cnt = int(match.group(1)) if match.group(1) else 1
            sym = match.group(2).upper()
            seq.extend([sym] * cnt)
        else:
            sym_match = re.search(r'[A-Za-z]+', item)
            sym = sym_match.group().upper() if sym_match else "X"
            num_match = re.search(r'\d+', item)
            cnt = int(num_match.group()) if num_match else 1
            seq.extend([sym] * cnt)

    return seq * repeat

def draw_diagram(rounds, highlight_rnd=None, highlight_idx=None):
    """根據紀錄資料產生 Matplotlib 織圖，支援節點偏移與高亮"""
    if not rounds: return None
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_aspect('equal')
    ax.axis('off')

    start_type = rounds[0].get("type", "magic_ring") if len(rounds) > 0 else "magic_ring"

    if start_type == "magic_ring":
        base_radius = 2
        for i, rnd in enumerate(rounds):
            if rnd["type"] == "magic_ring":
                circle = plt.Circle((0, 0), 0.5, color='gray', fill=False, linewidth=2)
                ax.add_patch(circle)
            else:
                r = base_radius * i
                circle = plt.Circle((0, 0), r, color='lightgray', fill=False, linestyle=':')
                ax.add_patch(circle)
                
                flat_symbols = rnd.get("flat_symbols", [rnd.get("symbol", "X")] * rnd.get("count", 6))
                count = len(flat_symbols)
                if count == 0: continue
                
                angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
                for j, (angle, symbol) in enumerate(zip(angles, flat_symbols)):
                    x = r * math.cos(angle)
                    y = r * math.sin(angle)
                    
                    # 疊加微調偏移量 (Offsets)
                    offsets = rnd.get("offsets", {})
                    dx, dy = offsets.get(str(j), [0.0, 0.0])
                    x += float(dx)
                    y += float(dy)
                    
                    rotation_deg = math.degrees(angle) - 90
                    
                    # 高亮被選中的針目
                    is_highlight = (i == highlight_rnd and j == highlight_idx)
                    color = 'red' if is_highlight else 'black'
                    fontsize = 18 if is_highlight else 14
                    
                    ax.text(x, y, symbol, ha='center', va='center', rotation=rotation_deg, fontsize=fontsize, fontweight='bold', color=color)
                    
        max_r = base_radius * len(rounds)
        ax.set_xlim(-max_r, max_r)
        ax.set_ylim(-max_r, max_r)

    elif start_type == "chain_start":
        max_x = 0
        for i, rnd in enumerate(rounds):
            y = i * 1.5 
            
            if rnd["type"] == "chain_start":
                flat_symbols = ["CH"] * rnd.get("count", 1)
            else:
                flat_symbols = rnd.get("flat_symbols", [rnd.get("symbol", "X")] * rnd.get("count", 1))

            count = len(flat_symbols)
            if count == 0: continue

            if count == 1: xs = [0]
            else: xs = np.linspace(-count/2 + 0.5, count/2 - 0.5, count)

            max_x = max(max_x, count/2)

            if count > 1: ax.plot([xs[0], xs[-1]], [y, y], color='lightgray', linestyle=':', zorder=1)

            for j, (x, symbol) in enumerate(zip(xs, flat_symbols)):
                # 疊加微調偏移量 (Offsets)
                offsets = rnd.get("offsets", {})
                dx, dy = offsets.get(str(j), [0.0, 0.0])
                x_final = x + float(dx)
                y_final = y + float(dy)
                
                is_highlight = (i == highlight_rnd and j == highlight_idx)
                color = 'red' if is_highlight else 'black'
                fontsize = 18 if is_highlight else 14
                
                ax.text(x_final, y_final, symbol, ha='center', va='center', fontsize=fontsize, fontweight='bold', color=color, zorder=2)

        ax.set_xlim(-max_x - 1, max_x + 1)
        ax.set_ylim(-1, len(rounds) * 1.5)

    return fig

def print_diagram_summary(rounds):
    """印出單一區段的圖解文字摘要"""
    for i, rnd in enumerate(rounds):
        if rnd["type"] == "magic_ring": st.caption("起針：環形起針")
        elif rnd["type"] == "chain_start": st.caption(f"起針：辮子起針 ({rnd.get('count', 0)} 針)")
        else:
            if "original_str" in rnd:
                seq_str = rnd["original_str"]
                tot = len(rnd.get("flat_symbols", []))
                st.caption(f"第 {i} 圈/排：{seq_str} ＝ 共 **{tot}** 針")
            else:
                seq_str = " + ".join([f"{item['symbol']}*{item['count']}" for item in rnd.get("sequence", [])])
                rep = rnd.get("repeat", 1)
                tot = rnd.get("total_stitches", len(rnd.get("flat_symbols", [])))
                if not seq_str:
                    seq_str = f"{rnd.get('symbol', 'X')}*{rnd.get('count', 6)}"
                    rep = 1
                st.caption(f"第 {i} 圈/排：({seq_str}) * {rep} 次 ＝ 共 **{tot}** 針")

def render_diagram_preview(diagram_sections, state_key=None, is_editable=True):
    """渲染多個區段的圖解預覽，並提供手動微調工具"""
    if not diagram_sections:
        st.info("目前尚無圖解資料。請點擊上方按鈕產生。")
        return
        
    highlight_sec = None
    highlight_rnd = None
    highlight_idx = None
        
    # --- 位置微調工具區 (僅在編輯模式顯示) ---
    if is_editable and state_key:
        st.markdown("#### 🎛️ 針目位置微調工具")
        st.info("💡 如果覺得符號太擠，可選擇特定針目，用滑桿微調 X/Y 位置。(圖上的紅字即為目前選取的針目)")
        
        sec_names = [sec.get("name", f"區段 {i+1}") for i, sec in enumerate(diagram_sections)]
        
        col_adj1, col_adj2, col_adj3 = st.columns(3)
        with col_adj1:
            sel_sec_name = st.selectbox("選擇區段", sec_names, key=f"{state_key}_adj_sec")
            sel_sec_idx = sec_names.index(sel_sec_name)
            
        rounds = diagram_sections[sel_sec_idx].get("rounds", [])
        
        # 過濾出有針目的圈/排
        valid_rounds = []
        for i, r in enumerate(rounds):
            if r.get("type") == "chain_start" and r.get("count", 0) > 0: valid_rounds.append(i)
            elif "flat_symbols" in r and len(r["flat_symbols"]) > 0: valid_rounds.append(i)
            
        if valid_rounds:
            with col_adj2:
                sel_rnd_idx = st.selectbox("選擇圈/排數", valid_rounds, format_func=lambda x: f"第 {x} 圈/排", key=f"{state_key}_adj_rnd")
                
            if rounds[sel_rnd_idx].get("type") == "chain_start":
                flat_symbols = ["CH"] * rounds[sel_rnd_idx].get("count", 1)
            else:
                flat_symbols = rounds[sel_rnd_idx].get("flat_symbols", [])
                
            stitch_opts = [i for i in range(len(flat_symbols))]
            
            with col_adj3:
                sel_stitch_idx = st.selectbox("選擇針目", stitch_opts, format_func=lambda x: f"第 {x+1} 針 ({flat_symbols[x]})", key=f"{state_key}_adj_stitch")
                
            # 讀取現有的偏移量
            offsets = rounds[sel_rnd_idx].get("offsets", {})
            current_dx, current_dy = offsets.get(str(sel_stitch_idx), [0.0, 0.0])
            
            col_sl1, col_sl2 = st.columns(2)
            with col_sl1:
                new_dx = st.slider("左右微調 (X軸偏移)", min_value=-3.0, max_value=3.0, value=float(current_dx), step=0.1, key=f"{state_key}_dx")
            with col_sl2:
                new_dy = st.slider("上下微調 (Y軸偏移)", min_value=-3.0, max_value=3.0, value=float(current_dy), step=0.1, key=f"{state_key}_dy")
                
            # 若數值有變動則存入結構中
            if new_dx != float(current_dx) or new_dy != float(current_dy):
                if "offsets" not in rounds[sel_rnd_idx]:
                    rounds[sel_rnd_idx]["offsets"] = {}
                rounds[sel_rnd_idx]["offsets"][str(sel_stitch_idx)] = [float(new_dx), float(new_dy)]
            
            highlight_sec = sel_sec_idx
            highlight_rnd = sel_rnd_idx
            highlight_idx = sel_stitch_idx
        else:
            st.warning("此區段目前沒有可調整的針目。")

        st.write("---")

    # --- 繪圖預覽區 ---
    for i, sec in enumerate(diagram_sections):
        st.markdown(f"#### 📍 {sec.get('name', '區段')}")
        rounds_data = sec.get('rounds', [])
        if rounds_data:
            if i == highlight_sec:
                fig = draw_diagram(rounds_data, highlight_rnd=highlight_rnd, highlight_idx=highlight_idx)
            else:
                fig = draw_diagram(rounds_data)
                
            if fig: st.pyplot(fig)
            print_diagram_summary(rounds_data)
        st.write("---")

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color_spec TEXT,
                quantity TEXT,
                notes TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT,
                yarn_req TEXT,
                hook_size TEXT,
                notes TEXT,
                file_path TEXT,
                sections_data TEXT,
                diagram_data TEXT
            )
        ''')
        try: c.execute("ALTER TABLE patterns ADD COLUMN sections_data TEXT")
        except sqlite3.OperationalError: pass
        try: c.execute("ALTER TABLE patterns ADD COLUMN diagram_data TEXT")
        except sqlite3.OperationalError: pass
            
        c.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                image_path TEXT,
                pattern_id INTEGER
            )
        ''')
        try: c.execute("ALTER TABLE projects ADD COLUMN pattern_id INTEGER")
        except sqlite3.OperationalError: pass
        conn.commit()

init_db()

# --- 側邊欄與頁面導航狀態控制 ---
pages_list = ["🏠 首頁 - 作品展示", "🧵 材料庫存", "📖 查看織圖", "➕ 新增織圖"]
if "current_page" not in st.session_state:
    st.session_state.current_page = pages_list[0]

st.sidebar.title("🧶 AI-Crochet")
selected_page = st.sidebar.radio(
    "請選擇頁面：",
    pages_list,
    index=pages_list.index(st.session_state.current_page)
)

if selected_page != st.session_state.current_page:
    st.session_state.current_page = selected_page
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.info("歡迎來到你的專屬勾針創作紀錄系統！")

page = st.session_state.current_page

# --- 頁面內容 ---
if page == "🏠 首頁 - 作品展示":
    st.title("🏠 我的勾針作品展示區")
    st.write("這裡是你的作品藝廊！")
    
    with get_connection() as conn:
        patterns_df = pd.read_sql("SELECT id, name FROM patterns", conn)
    pattern_list = ["(無關聯)"] + [f"{p['id']} - {p['name']}" for _, p in patterns_df.iterrows()]
    
    with st.expander("➕ 新增完成的作品到展示區"):
        with st.form("add_project_form", clear_on_submit=True):
            proj_name = st.text_input("作品名稱 *")
            proj_desc = st.text_area("作品描述 / 心得")
            proj_pattern = st.selectbox("關聯織圖 (選填)", pattern_list)
            proj_image = st.file_uploader("上傳作品照片", type=["jpg", "png", "jpeg"])
            
            if st.form_submit_button("新增作品"):
                if proj_name and proj_image:
                    file_path = os.path.join(UPLOAD_DIR, proj_image.name)
                    with open(file_path, "wb") as f: f.write(proj_image.getbuffer())
                    
                    pat_id = None if proj_pattern == "(無關聯)" else int(proj_pattern.split(" - ")[0])
                    
                    with get_connection() as conn:
                        c = conn.cursor()
                        c.execute("INSERT INTO projects (name, description, image_path, pattern_id) VALUES (?, ?, ?, ?)",
                                  (proj_name, proj_desc, file_path, pat_id))
                        conn.commit()
                    st.success("✅ 作品新增成功！")
                    st.rerun() 
                else:
                    st.error("請填寫作品名稱並上傳照片！")

    st.divider()

    with get_connection() as conn:
        projects_df = pd.read_sql("SELECT * FROM projects", conn)

    if projects_df.empty:
        st.info("目前還沒有展示的作品，快點擊上方按鈕新增一個吧！")
    else:
        cols = st.columns(3)
        for index, row in projects_df.iterrows():
            col = cols[index % 3]
            with col:
                with st.container(border=True):
                    if os.path.exists(row['image_path']):
                        st.image(row['image_path'], use_container_width=True)
                    else:
                        st.error("找不到圖片檔案")
                    st.subheader(row['name'])
                    if row['description']:
                        st.write(row['description'])
                        
                    st.divider()
                    
                    if pd.notna(row.get('pattern_id')):
                        if st.button("🔗 查看對應織圖", key=f"view_pat_{row['id']}", use_container_width=True):
                            st.session_state.current_page = "📖 查看織圖"
                            st.session_state.target_pattern_id = int(row['pattern_id'])
                            st.rerun()
                    
                    col_edit, col_del = st.columns([1, 1])
                    with col_del:
                        if st.button("🗑️ 刪除", key=f"del_proj_{row['id']}", use_container_width=True):
                            with get_connection() as conn:
                                c = conn.cursor()
                                c.execute("DELETE FROM projects WHERE id=?", (row['id'],))
                                conn.commit()
                            if os.path.exists(row['image_path']):
                                try: os.remove(row['image_path'])
                                except Exception: pass
                            st.rerun()
                            
                    with col_edit:
                        edit_expander = st.expander("✏️ 編輯")
                        
                    with edit_expander:
                        with st.form(f"edit_form_{row['id']}", clear_on_submit=False):
                            new_name = st.text_input("修改名稱", value=row['name'])
                            new_desc = st.text_area("修改描述", value=row['description'] if row['description'] else "")
                            
                            current_pat_idx = 0
                            if pd.notna(row.get('pattern_id')):
                                for i, p_str in enumerate(pattern_list):
                                    if p_str.startswith(f"{int(row['pattern_id'])} -"):
                                        current_pat_idx = i
                                        break
                                        
                            new_pat = st.selectbox("修改關聯織圖", pattern_list, index=current_pat_idx)
                            new_image = st.file_uploader("更換照片 (若不更換請留白)", type=["jpg", "png", "jpeg"])
                            
                            if st.form_submit_button("💾 儲存修改", use_container_width=True):
                                update_path = row['image_path']
                                if new_image:
                                    update_path = os.path.join(UPLOAD_DIR, new_image.name)
                                    with open(update_path, "wb") as f: f.write(new_image.getbuffer())
                                        
                                new_pat_id = None if new_pat == "(無關聯)" else int(new_pat.split(" - ")[0])
                                
                                with get_connection() as conn:
                                    c = conn.cursor()
                                    c.execute("UPDATE projects SET name=?, description=?, image_path=?, pattern_id=? WHERE id=?",
                                              (new_name, new_desc, update_path, new_pat_id, row['id']))
                                    conn.commit()
                                st.success("✅ 更新成功！")
                                st.rerun()

elif page == "🧵 材料庫存":
    st.title("🧵 材料庫存管理")
    st.write("在這裡管理你的毛線、勾針尺寸與其他配件。")
    
    with st.expander("➕ 新增材料"):
        with st.form("add_material_form", clear_on_submit=True):
            mat_name = st.text_input("材料名稱 (如: 牛奶棉 5股) *")
            mat_color = st.text_input("顏色/規格 (如: 鵝黃色, 2.0mm)")
            mat_qty = st.text_input("數量 (如: 3 捲)")
            mat_notes = st.text_input("備註 (如: 預計做嬰兒帽)")
            
            if st.form_submit_button("儲存材料"):
                if mat_name:
                    with get_connection() as conn:
                        c = conn.cursor()
                        c.execute("INSERT INTO materials (name, color_spec, quantity, notes) VALUES (?, ?, ?, ?)",
                                  (mat_name, mat_color, mat_qty, mat_notes))
                        conn.commit()
                    st.success("✅ 材料新增成功！")
                    st.rerun()
                else:
                    st.error("請至少填寫材料名稱！")

    with get_connection() as conn:
        df = pd.read_sql("SELECT id, name, color_spec, quantity, notes FROM materials", conn)
    
    if df.empty:
        st.info("目前沒有庫存紀錄，請從上方新增。")
    else:
        st.write("💡 **提示：** 您可以直接在下方表格內點擊儲存格來修改文字。若要刪除資料，請點選該列最左側的方塊並按鍵盤 `Delete` 鍵。修改完成後，請務必點擊底部的「儲存庫存變更」！")
        
        edited_df = st.data_editor(
            df,
            column_config={
                "id": None, 
                "name": st.column_config.TextColumn("材料名稱 *", required=True),
                "color_spec": st.column_config.TextColumn("顏色/規格"),
                "quantity": st.column_config.TextColumn("數量"),
                "notes": st.column_config.TextColumn("備註"),
            },
            use_container_width=True,
            num_rows="dynamic",
            key="inventory_editor"
        )
        
        if st.button("💾 儲存庫存變更", type="primary", use_container_width=True):
            editor_state = st.session_state["inventory_editor"]
            with get_connection() as conn:
                c = conn.cursor()
                deleted_rows = editor_state.get("deleted_rows", [])
                if deleted_rows:
                    ids_to_delete = [int(df.iloc[idx]['id']) for idx in deleted_rows]
                    c.executemany("DELETE FROM materials WHERE id=?", [(i,) for i in ids_to_delete])
                
                edited_rows = editor_state.get("edited_rows", {})
                for idx, changes in edited_rows.items():
                    row_id = int(df.iloc[idx]['id'])
                    current_row = df.iloc[idx].to_dict()
                    current_row.update(changes)
                    c.execute("UPDATE materials SET name=?, color_spec=?, quantity=?, notes=? WHERE id=?",
                              (current_row.get('name'), current_row.get('color_spec'), current_row.get('quantity'), current_row.get('notes'), row_id))
                              
                added_rows = editor_state.get("added_rows", [])
                for new_row in added_rows:
                    if new_row.get('name'):
                        c.execute("INSERT INTO materials (name, color_spec, quantity, notes) VALUES (?, ?, ?, ?)",
                                  (new_row.get('name', ''), new_row.get('color_spec', ''), new_row.get('quantity', ''), new_row.get('notes', '')))
                conn.commit()
            st.success("✅ 庫存變更已成功儲存！")
            st.rerun()

elif page == "📖 查看織圖":
    if "edit_pattern_id" not in st.session_state:
        st.session_state.edit_pattern_id = None

    if st.session_state.edit_pattern_id is not None:
        # === 模式 B：編輯單一織圖介面 ===
        st.title("✏️ 編輯織圖")
        pattern_id = st.session_state.edit_pattern_id
        
        with get_connection() as conn:
            df_edit = pd.read_sql(f"SELECT * FROM patterns WHERE id={pattern_id}", conn)
            
        if df_edit.empty:
            st.error("找不到該筆資料！")
            if st.button("返回"):
                st.session_state.edit_pattern_id = None
                st.rerun()
        else:
            row = df_edit.iloc[0]
            
            if "edit_gen_sections" not in st.session_state:
                if row.get('diagram_data') and row['diagram_data']:
                    try: 
                        loaded_diag = json.loads(row['diagram_data'])
                        if isinstance(loaded_diag, list) and len(loaded_diag) > 0 and "rounds" not in loaded_diag[0]:
                            loaded_diag = [{"name": "預設區段", "rounds": loaded_diag}]
                        st.session_state.edit_gen_sections = loaded_diag
                    except: st.session_state.edit_gen_sections = []
                else: st.session_state.edit_gen_sections = []

            new_name = st.text_input("織圖名稱 *", value=row['name'])
            types = ["玩偶 (Amigurumi)", "服飾", "包包", "家飾", "其他"]
            type_idx = types.index(row['type']) if row['type'] in types else 0
            new_type = st.selectbox("分類", types, index=type_idx)
            
            col1, col2 = st.columns(2)
            with col1: new_yarn = st.text_input("建議線材", value=row['yarn_req'] if row['yarn_req'] else "")
            with col2: new_hook = st.text_input("建議勾針尺寸", value=row['hook_size'] if row['hook_size'] else "")
                
            new_file = st.file_uploader("更換織圖檔案 (若不更換請留白)", type=["jpg", "png", "jpeg", "pdf"])
            new_notes = st.text_area("整體筆記 / 心得", value=row['notes'] if row['notes'] else "")
            
            st.divider()

            if "edit_pattern_sections" not in st.session_state:
                if row['sections_data']:
                    try:
                        loaded_sections = json.loads(row['sections_data'])
                        for sec in loaded_sections: sec['data'] = pd.DataFrame(sec['data'])
                        st.session_state.edit_pattern_sections = loaded_sections
                    except Exception: st.session_state.edit_pattern_sections = [{"name": "區段 1", "data": pd.DataFrame([{"圈數": "1", "針法": "", "針數": "", "備註": ""}])}]
                else: st.session_state.edit_pattern_sections = [{"name": "區段 1", "data": pd.DataFrame([{"圈數": "1", "針法": "", "針數": "", "備註": ""}])}]
            
            st.subheader("📝 編輯織法表格")
            sections_to_remove = []
            needs_rerun = False
            for i, sec in enumerate(st.session_state.edit_pattern_sections):
                scol1, scol2 = st.columns([4, 1])
                with scol1: sec['name'] = st.text_input("區段名稱", value=sec['name'], key=f"edit_sec_name_{i}")
                with scol2:
                    st.write(""); st.write("")
                    if st.button("🗑️ 刪除區段", key=f"edit_del_sec_{i}"): sections_to_remove.append(i)
                        
                edited_df = st.data_editor(
                    sec['data'],
                    num_rows="dynamic",
                    key=f"edit_editor_{i}",
                    use_container_width=True,
                    column_config={
                        "圈數": st.column_config.TextColumn("圈數"),
                        "針法": st.column_config.TextColumn("針法"),
                        "針數": st.column_config.TextColumn("總針數"),
                        "備註": st.column_config.TextColumn("備註"),
                    }
                )
                
                section_updated = False
                for idx in range(len(edited_df)):
                    current_val = str(edited_df.iloc[idx]['圈數'])
                    if idx == 0:
                        if pd.isna(edited_df.iloc[idx]['圈數']) or current_val.strip() == "":
                            edited_df.at[edited_df.index[idx], '圈數'] = "1"
                            section_updated = True
                    else:
                        prev_val = str(edited_df.iloc[idx-1]['圈數'])
                        match = re.search(r'\d+', prev_val)
                        if match:
                            expected_val = prev_val.replace(match.group(), str(int(match.group()) + 1), 1)
                            if current_val != expected_val:
                                edited_df.at[edited_df.index[idx], '圈數'] = expected_val
                                section_updated = True
                        else:
                            expected_val = str(idx + 1)
                            if current_val != expected_val:
                                edited_df.at[edited_df.index[idx], '圈數'] = expected_val
                                section_updated = True
                
                if section_updated:
                    sec['data'] = edited_df
                    needs_rerun = True
                else:
                    sec['data'] = edited_df
                    
                builder_key = f"edit_sec_builder_{i}"
                if builder_key not in st.session_state: st.session_state[builder_key] = []
                    
                with st.expander("🛠️ 快速新增 / 組合建構器", expanded=False):
                    if st.session_state[builder_key]:
                        seq_strs = [f"{item['stitch']} x{item['count']}" for item in st.session_state[builder_key]]
                        st.info(f"**目前組合：** ( {' + '.join(seq_strs)} )")
                        
                    col_b1, col_b2, col_b3, col_b4 = st.columns([3, 2, 2.5, 2.5])
                    with col_b1: stitch_type = st.selectbox("選擇針法", STITCH_OPTIONS, key=f"edit_b_stitch_{i}")
                    with col_b2: stitch_count = st.number_input("針數", min_value=1, value=1, step=1, key=f"edit_b_cnt_{i}")
                    with col_b3:
                        st.write(""); st.write("")
                        if st.button("✅ 直接新增一圈", type="primary", use_container_width=True, key=f"edit_b_direct_{i}"):
                            symbol_match = re.search(r'[A-Za-z]+', stitch_type)
                            symbol = symbol_match.group() if symbol_match else "X"
                            weight = STITCH_WEIGHTS.get(symbol, 1)
                            total_stitches = weight * stitch_count
                            final_stitch_str = f"{symbol}" if stitch_count==1 else f"{stitch_count}{symbol}"
                            
                            next_round = "1"
                            if len(edited_df) > 0:
                                prev_val = edited_df.iloc[-1]['圈數']
                                match = re.search(r'\d+', str(prev_val))
                                if match: next_round = str(prev_val).replace(match.group(), str(int(match.group()) + 1), 1)
                                else: next_round = str(len(edited_df) + 1)

                            new_row = {"圈數": next_round, "針法": final_stitch_str, "針數": str(total_stitches), "備註": ""}
                            sec['data'] = pd.concat([edited_df, pd.DataFrame([new_row])], ignore_index=True)
                            st.rerun()
                    with col_b4:
                        st.write(""); st.write("")
                        if st.button("➕ 加入組合", use_container_width=True, key=f"edit_b_add_{i}"):
                            symbol_match = re.search(r'[A-Za-z]+', stitch_type)
                            symbol = symbol_match.group() if symbol_match else "X"
                            st.session_state[builder_key].append({
                                "stitch": stitch_type, "symbol": symbol, "count": stitch_count
                            })
                            st.rerun()
                            
                    if st.session_state[builder_key]:
                        col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
                        with col_r1:
                            repeat_times = st.number_input("上述組合重複幾次?", min_value=1, value=1, step=1, key=f"edit_b_rep_{i}")
                            notes_input = st.text_input("備註 (選填)", key=f"edit_b_notes_{i}")
                        with col_r2:
                            st.write(""); st.write("")
                            if st.button("✅ 產生並加入表格", type="primary", key=f"edit_b_done_{i}"):
                                total_stitches = 0
                                seq_symbols = []
                                for item in st.session_state[builder_key]:
                                    weight = STITCH_WEIGHTS.get(item["symbol"], 1)
                                    total_stitches += weight * item["count"]
                                    seq_symbols.append(f"{item['symbol']}" if item['count']==1 else f"{item['count']}{item['symbol']}")
                                
                                total_stitches *= repeat_times
                                seq_str = ", ".join(seq_symbols)
                                final_stitch_str = f"({seq_str}) * {repeat_times}" if repeat_times > 1 else (seq_str if len(seq_symbols) > 1 else seq_symbols[0])

                                next_round = "1"
                                if len(edited_df) > 0:
                                    prev_val = edited_df.iloc[-1]['圈數']
                                    match = re.search(r'\d+', str(prev_val))
                                    if match: next_round = str(prev_val).replace(match.group(), str(int(match.group()) + 1), 1)
                                    else: next_round = str(len(edited_df) + 1)

                                new_row = {"圈數": next_round, "針法": final_stitch_str, "針數": str(total_stitches), "備註": notes_input}
                                sec['data'] = pd.concat([edited_df, pd.DataFrame([new_row])], ignore_index=True)
                                st.session_state[builder_key] = []
                                st.rerun()
                        with col_r3:
                            st.write(""); st.write("")
                            if st.button("🗑️ 清空組合", key=f"edit_b_clear_{i}"):
                                st.session_state[builder_key] = []
                                st.rerun()
                st.write("---")
                
            if sections_to_remove:
                for idx in sorted(sections_to_remove, reverse=True): st.session_state.edit_pattern_sections.pop(idx)
                st.rerun()
            elif needs_rerun: st.rerun()
                
            if st.button("➕ 新增下一個區段"):
                new_idx = len(st.session_state.edit_pattern_sections) + 1
                st.session_state.edit_pattern_sections.append({
                    "name": f"區段 {new_idx}",
                    "data": pd.DataFrame([{"圈數": "1", "針法": "", "針數": "", "備註": ""}])
                })
                st.rerun()
                
            st.divider()

            with st.expander("🪄 編輯自動化圖解 (由表格產生)", expanded=True):
                if st.button("🔄 一鍵將上方表格資料匯入織圖產生器", type="primary", use_container_width=True, key="edit_sync_btn"):
                    new_sections = []
                    for sec in st.session_state.edit_pattern_sections:
                        new_rounds = []
                        is_first_row = True
                        for _, r in sec['data'].iterrows():
                            stitch_str = str(r['針法'])
                            flat_syms = parse_stitch_string(stitch_str)
                            if not flat_syms: continue
                            
                            if is_first_row:
                                is_first_row = False
                                if "CH" in stitch_str.upper() or "鎖" in stitch_str:
                                    new_rounds.append({"type": "chain_start", "count": len(flat_syms), "symbol": "CH"})
                                    continue
                                else:
                                    new_rounds.append({"type": "magic_ring"})
                                    
                            new_rounds.append({"type": "round", "flat_symbols": flat_syms, "count": len(flat_syms), "original_str": stitch_str})
                        
                        if new_rounds: new_sections.append({"name": sec['name'], "rounds": new_rounds})
                            
                    st.session_state.edit_gen_sections = new_sections
                    st.success("✅ 圖解資料轉換成功！現在可以使用下方的微調工具了。")
                    st.rerun()

                st.write("---")
                if "edit_gen_sections" in st.session_state:
                    render_diagram_preview(st.session_state.edit_gen_sections, state_key="edit_gen_sections", is_editable=True)
                
            st.divider()
            
            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.button("💾 儲存修改", type="primary", use_container_width=True):
                    if new_name:
                        update_path = row['file_path']
                        if new_file is not None:
                            update_path = os.path.join(UPLOAD_DIR, new_file.name)
                            with open(update_path, "wb") as f: f.write(new_file.getbuffer())
                                
                        save_data = []
                        for sec in st.session_state.edit_pattern_sections:
                            save_data.append({"name": sec['name'], "data": sec['data'].to_dict(orient="records")})
                        sections_json = json.dumps(save_data, ensure_ascii=False)
                        diagram_json = json.dumps(st.session_state.get("edit_gen_sections", []), ensure_ascii=False)
                        
                        with get_connection() as conn:
                            c = conn.cursor()
                            c.execute('''UPDATE patterns 
                                         SET name=?, type=?, yarn_req=?, hook_size=?, notes=?, file_path=?, sections_data=?, diagram_data=?
                                         WHERE id=?''', 
                                      (new_name, new_type, new_yarn, new_hook, new_notes, update_path, sections_json, diagram_json, pattern_id))
                            conn.commit()
                        
                        st.success("✅ 織圖更新成功！")
                        st.session_state.edit_pattern_id = None
                        if "edit_pattern_sections" in st.session_state: del st.session_state.edit_pattern_sections
                        if "edit_gen_sections" in st.session_state: del st.session_state.edit_gen_sections
                        st.rerun()
                    else: st.error("請填寫織圖名稱！")
                        
            with col_cancel:
                if st.button("❌ 取消編輯", use_container_width=True):
                    st.session_state.edit_pattern_id = None
                    if "edit_pattern_sections" in st.session_state: del st.session_state.edit_pattern_sections
                    if "edit_gen_sections" in st.session_state: del st.session_state.edit_gen_sections
                    st.rerun()

    else:
        # === 模式 A：織圖列表瀏覽模式 ===
        st.title("📖 織圖庫")
        
        target_id = st.session_state.get("target_pattern_id", None)
        
        if target_id is not None:
            st.info("🎯 正在為你展示來自首頁「作品」的專屬關聯織圖")
            if st.button("🔙 返回顯示所有織圖", type="primary"):
                st.session_state.target_pattern_id = None
                st.rerun()
            st.write("---")
        else:
            st.write("你收藏與紀錄的所有織圖都在這裡。")
        
        search_query = st.text_input("🔍 搜尋織圖名稱或分類...")
        
        with get_connection() as conn:
            if target_id is not None:
                query = f"SELECT * FROM patterns WHERE id={target_id}"
                patterns_df = pd.read_sql(query, conn)
            elif search_query:
                query = f"SELECT * FROM patterns WHERE name LIKE '%{search_query}%' OR type LIKE '%{search_query}%'"
                patterns_df = pd.read_sql(query, conn)
            else:
                patterns_df = pd.read_sql("SELECT * FROM patterns", conn)
                
        if patterns_df.empty:
            st.info("找不到符合的織圖。")
        else:
            for index, row in patterns_df.iterrows():
                auto_expand = (target_id is not None)
                with st.expander(f"🌸 {row['name']} ({row['type']})", expanded=auto_expand):
                    st.write(f"**建議線材：** {row['yarn_req']}")
                    st.write(f"**建議勾針：** {row['hook_size']}")
                    st.write(f"**整體筆記：** {row['notes']}")
                    
                    if row.get('diagram_data') and row['diagram_data']:
                        try:
                            diag_data = json.loads(row['diagram_data'])
                            if diag_data:
                                st.divider()
                                st.markdown("#### 🪄 圖解預覽")
                                if isinstance(diag_data, list) and len(diag_data) > 0 and "rounds" not in diag_data[0]:
                                    diag_data = [{"name": "預設區段", "rounds": diag_data}]
                                # 瀏覽模式不顯示微調工具
                                render_diagram_preview(diag_data, is_editable=False)
                        except Exception: pass
                    
                    if 'sections_data' in row and row['sections_data']:
                        try:
                            sections = json.loads(row['sections_data'])
                            if sections:
                                st.divider()
                                st.markdown("#### 📝 織法紀錄")
                                for sec in sections:
                                    st.markdown(f"**📍 {sec['name']}**")
                                    sec_df = pd.DataFrame(sec['data'])
                                    st.dataframe(sec_df, use_container_width=True, hide_index=True)
                        except Exception as e: st.error(f"無法解析表格資料: {e}")
                    
                    if row['file_path'] and os.path.exists(row['file_path']):
                        file_name = os.path.basename(row['file_path'])
                        with open(row['file_path'], "rb") as f:
                            btn = st.download_button(
                                label="📥 下載/查看附檔", data=f, file_name=file_name,
                                mime="application/octet-stream", key=f"dl_btn_{row['id']}"
                            )
                            
                    st.divider()
                    col_btn1, col_btn2 = st.columns([1, 1])
                    with col_btn1:
                        if st.button("✏️ 編輯此織圖", key=f"edit_btn_{row['id']}", use_container_width=True):
                            st.session_state.edit_pattern_id = row['id']
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ 刪除", key=f"del_pat_{row['id']}", use_container_width=True):
                            with get_connection() as conn:
                                c = conn.cursor()
                                c.execute("DELETE FROM patterns WHERE id=?", (row['id'],))
                                conn.commit()
                            if row['file_path'] and os.path.exists(row['file_path']):
                                try: os.remove(row['file_path'])
                                except Exception: pass
                            st.rerun()

elif page == "➕ 新增織圖":
    st.title("➕ 新增織圖")
    st.write("將新的靈感、織法區段和表格記錄下來吧！")
    
    if "pattern_sections" not in st.session_state:
        st.session_state.pattern_sections = [{
            "name": "區段 1 (例如：頭部)",
            "data": pd.DataFrame([{"圈數": "1", "針法": "6X", "針數": "6", "備註": "起針"}])
        }]
    
    pattern_name = st.text_input("織圖名稱 *", key="p_name")
    pattern_type = st.selectbox("分類", ["玩偶 (Amigurumi)", "服飾", "包包", "家飾", "其他"], key="p_type")
    
    col1, col2 = st.columns(2)
    with col1: yarn_req = st.text_input("建議線材", key="p_yarn")
    with col2: hook_size = st.text_input("建議勾針尺寸 (例如: 3.0mm, 5/0)", key="p_hook")
        
    uploaded_file = st.file_uploader("上傳織圖檔案 (圖片或 PDF)", type=["jpg", "png", "jpeg", "pdf"], key="p_file")
    notes = st.text_area("整體筆記 / 心得", key="p_notes")
    
    st.divider()
    
    st.subheader("📝 織法表格 (支援多區段)")
    st.info("💡 提示：若刪除中間的圈數，後續的編號將自動向前遞補喔！")
    
    sections_to_remove = []
    needs_rerun = False
    for i, sec in enumerate(st.session_state.pattern_sections):
        scol1, scol2 = st.columns([4, 1])
        with scol1: sec['name'] = st.text_input("區段名稱", value=sec['name'], key=f"sec_name_{i}")
        with scol2:
            st.write(""); st.write("")
            if st.button("🗑️ 刪除區段", key=f"del_sec_{i}"): sections_to_remove.append(i)
                
        edited_df = st.data_editor(
            sec['data'],
            num_rows="dynamic",
            key=f"editor_{i}",
            use_container_width=True,
            column_config={
                "圈數": st.column_config.TextColumn("圈數"),
                "針法": st.column_config.TextColumn("針法"),
                "針數": st.column_config.TextColumn("總針數 (例如: 6, 12)"),
                "備註": st.column_config.TextColumn("備註"),
            }
        )
        
        section_updated = False
        for idx in range(len(edited_df)):
            current_val = str(edited_df.iloc[idx]['圈數'])
            if idx == 0:
                if pd.isna(edited_df.iloc[idx]['圈數']) or current_val.strip() == "":
                    edited_df.at[edited_df.index[idx], '圈數'] = "1"
                    section_updated = True
            else:
                prev_val = str(edited_df.iloc[idx-1]['圈數'])
                match = re.search(r'\d+', prev_val)
                if match:
                    expected_val = prev_val.replace(match.group(), str(int(match.group()) + 1), 1)
                    if current_val != expected_val:
                        edited_df.at[edited_df.index[idx], '圈數'] = expected_val
                        section_updated = True
                else:
                    expected_val = str(idx + 1)
                    if current_val != expected_val:
                        edited_df.at[edited_df.index[idx], '圈數'] = expected_val
                        section_updated = True
        
        if section_updated:
            sec['data'] = edited_df
            needs_rerun = True
        else:
            sec['data'] = edited_df

        builder_key = f"sec_builder_{i}"
        if builder_key not in st.session_state: st.session_state[builder_key] = []
            
        with st.expander("🛠️ 快速新增 / 組合建構器", expanded=True):
            if st.session_state[builder_key]:
                seq_strs = [f"{item['stitch']} x{item['count']}" for item in st.session_state[builder_key]]
                st.info(f"**目前組合：** ( {' + '.join(seq_strs)} )")
                
            col_b1, col_b2, col_b3, col_b4 = st.columns([3, 2, 2.5, 2.5])
            with col_b1: stitch_type = st.selectbox("選擇針法", STITCH_OPTIONS, key=f"b_stitch_{i}")
            with col_b2: stitch_count = st.number_input("針數", min_value=1, value=1, step=1, key=f"b_cnt_{i}")
            with col_b3:
                st.write(""); st.write("")
                if st.button("✅ 直接新增一圈", type="primary", use_container_width=True, key=f"b_direct_{i}"):
                    symbol_match = re.search(r'[A-Za-z]+', stitch_type)
                    symbol = symbol_match.group() if symbol_match else "X"
                    weight = STITCH_WEIGHTS.get(symbol, 1)
                    total_stitches = weight * stitch_count
                    final_stitch_str = f"{symbol}" if stitch_count==1 else f"{stitch_count}{symbol}"
                    
                    next_round = "1"
                    if len(edited_df) > 0:
                        prev_val = edited_df.iloc[-1]['圈數']
                        match = re.search(r'\d+', str(prev_val))
                        if match: next_round = str(prev_val).replace(match.group(), str(int(match.group()) + 1), 1)
                        else: next_round = str(len(edited_df) + 1)

                    new_row = {"圈數": next_round, "針法": final_stitch_str, "針數": str(total_stitches), "備註": ""}
                    sec['data'] = pd.concat([edited_df, pd.DataFrame([new_row])], ignore_index=True)
                    st.rerun()
            with col_b4:
                st.write(""); st.write("")
                if st.button("➕ 加入組合", use_container_width=True, key=f"b_add_{i}"):
                    symbol_match = re.search(r'[A-Za-z]+', stitch_type)
                    symbol = symbol_match.group() if symbol_match else "X"
                    st.session_state[builder_key].append({
                        "stitch": stitch_type, "symbol": symbol, "count": stitch_count
                    })
                    st.rerun()
                    
            if st.session_state[builder_key]:
                col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
                with col_r1:
                    repeat_times = st.number_input("上述組合重複幾次?", min_value=1, value=1, step=1, key=f"b_rep_{i}")
                    notes_input = st.text_input("備註 (選填)", key=f"b_notes_{i}")
                with col_r2:
                    st.write(""); st.write("")
                    if st.button("✅ 產生並加入表格", type="primary", key=f"b_done_{i}"):
                        total_stitches = 0
                        seq_symbols = []
                        for item in st.session_state[builder_key]:
                            weight = STITCH_WEIGHTS.get(item["symbol"], 1)
                            total_stitches += weight * item["count"]
                            seq_symbols.append(f"{item['symbol']}" if item['count']==1 else f"{item['count']}{item['symbol']}")
                        
                        total_stitches *= repeat_times
                        seq_str = ", ".join(seq_symbols)
                        final_stitch_str = f"({seq_str}) * {repeat_times}" if repeat_times > 1 else (seq_str if len(seq_symbols) > 1 else seq_symbols[0])

                        next_round = "1"
                        if len(edited_df) > 0:
                            prev_val = edited_df.iloc[-1]['圈數']
                            match = re.search(r'\d+', str(prev_val))
                            if match: next_round = str(prev_val).replace(match.group(), str(int(match.group()) + 1), 1)
                            else: next_round = str(len(edited_df) + 1)

                        new_row = {"圈數": next_round, "針法": final_stitch_str, "針數": str(total_stitches), "備註": notes_input}
                        sec['data'] = pd.concat([edited_df, pd.DataFrame([new_row])], ignore_index=True)
                        st.session_state[builder_key] = []
                        st.rerun()
                with col_r3:
                    st.write(""); st.write("")
                    if st.button("🗑️ 清空組合", key=f"b_clear_{i}"):
                        st.session_state[builder_key] = []
                        st.rerun()
                        
        st.write("---")
        
    if sections_to_remove:
        for idx in sorted(sections_to_remove, reverse=True): st.session_state.pattern_sections.pop(idx)
        st.rerun()
    elif needs_rerun: st.rerun()
        
    if st.button("➕ 新增下一個區段 (例如：手、身體)"):
        new_idx = len(st.session_state.pattern_sections) + 1
        st.session_state.pattern_sections.append({
            "name": f"區段 {new_idx}",
            "data": pd.DataFrame([{"圈數": "1", "針法": "", "針數": "", "備註": ""}])
        })
        st.rerun()
        
    st.divider()

    with st.expander("🪄 自動化織圖產生器 (由表格產生)", expanded=True):
        st.write("在上方表格完成編輯後，點擊下方按鈕即可一鍵繪製圖解！")
        if st.button("🔄 一鍵將上方表格資料匯入織圖產生器", type="primary", use_container_width=True, key="add_sync_btn"):
            new_sections = []
            for sec in st.session_state.pattern_sections:
                new_rounds = []
                is_first_row = True
                for _, r in sec['data'].iterrows():
                    stitch_str = str(r['針法'])
                    flat_syms = parse_stitch_string(stitch_str)
                    if not flat_syms: continue
                    
                    if is_first_row:
                        is_first_row = False
                        if "CH" in stitch_str.upper() or "鎖" in stitch_str:
                            new_rounds.append({"type": "chain_start", "count": len(flat_syms), "symbol": "CH"})
                            continue 
                        else: new_rounds.append({"type": "magic_ring"})
                            
                    new_rounds.append({"type": "round", "flat_symbols": flat_syms, "count": len(flat_syms), "original_str": stitch_str})
                
                if new_rounds: new_sections.append({"name": sec['name'], "rounds": new_rounds})
                    
            st.session_state.gen_sections = new_sections
            st.success("✅ 圖解資料轉換成功！現在可以使用下方的微調工具了。")
            st.rerun()

        st.write("---")
        if "gen_sections" in st.session_state:
            render_diagram_preview(st.session_state.gen_sections, state_key="gen_sections", is_editable=True)

    st.divider()
    
    if st.button("💾 儲存完整織圖", type="primary", use_container_width=True):
        if pattern_name:
            file_path = ""
            if uploaded_file is not None:
                file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
                with open(file_path, "wb") as f: f.write(uploaded_file.getbuffer())
            
            save_data = []
            for sec in st.session_state.pattern_sections:
                save_data.append({"name": sec['name'], "data": sec['data'].to_dict(orient="records")})
            sections_json = json.dumps(save_data, ensure_ascii=False)
            diagram_json = json.dumps(st.session_state.get("gen_sections", []), ensure_ascii=False)
            
            with get_connection() as conn:
                c = conn.cursor()
                c.execute('''INSERT INTO patterns 
                             (name, type, yarn_req, hook_size, notes, file_path, sections_data, diagram_data) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                          (pattern_name, pattern_type, yarn_req, hook_size, notes, file_path, sections_json, diagram_json))
                conn.commit()
            
            st.success(f"✅ 成功新增織圖：{pattern_name}！請至「查看織圖」頁面確認。")
            
            del st.session_state.pattern_sections
            if "gen_sections" in st.session_state: del st.session_state.gen_sections
            for key in ["p_name", "p_yarn", "p_hook", "p_notes"]:
                if key in st.session_state: st.session_state[key] = ""
            st.rerun()
        else:
            st.error("請填寫織圖名稱！")