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
    
    # 匹配 ( ... ) * N 或 ( ... ) x N
    match_repeat = re.search(r'\((.*?)\)\s*[\*xX]\s*(\d+)', stitch_str)
    if match_repeat:
        pattern_str = match_repeat.group(1)
        repeat = int(match_repeat.group(2))
    else:
        # 匹配 ... * N
        match_repeat_no_paren = re.search(r'(.*?)\s*[\*xX]\s*(\d+)$', stitch_str)
        if match_repeat_no_paren:
            pattern_str = match_repeat_no_paren.group(1)
            repeat = int(match_repeat_no_paren.group(2))

    items = [x.strip() for x in pattern_str.split(',')]
    seq = []
    for item in items:
        if not item: continue
        # 匹配 '2X', '10CH' 這類開頭有數字的
        match = re.match(r'^(\d+)?([A-Za-z]+)$', item)
        if match:
            cnt = int(match.group(1)) if match.group(1) else 1
            sym = match.group(2).upper()
            seq.extend([sym] * cnt)
        else:
            # 容錯處理：硬抓英文字母與數字
            sym_match = re.search(r'[A-Za-z]+', item)
            sym = sym_match.group().upper() if sym_match else "X"
            num_match = re.search(r'\d+', item)
            cnt = int(num_match.group()) if num_match else 1
            seq.extend([sym] * cnt)

    return seq * repeat

def draw_diagram(rounds):
    """根據紀錄資料產生 Matplotlib 織圖"""
    if not rounds: return None
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_aspect('equal')
    ax.axis('off')

    start_type = rounds[0].get("type", "magic_ring") if len(rounds) > 0 else "magic_ring"

    if start_type == "magic_ring":
        # === 環形起針繪圖邏輯 ===
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
                for angle, symbol in zip(angles, flat_symbols):
                    x = r * math.cos(angle)
                    y = r * math.sin(angle)
                    rotation_deg = math.degrees(angle) - 90
                    ax.text(x, y, symbol, ha='center', va='center', rotation=rotation_deg, fontsize=14, fontweight='bold')
                    
        max_r = base_radius * len(rounds)
        ax.set_xlim(-max_r, max_r)
        ax.set_ylim(-max_r, max_r)

    elif start_type == "chain_start":
        # === 辮子起針 (平織) 繪圖邏輯 ===
        max_x = 0
        for i, rnd in enumerate(rounds):
            y = i * 1.5 
            
            if rnd["type"] == "chain_start":
                flat_symbols = ["CH"] * rnd.get("count", 1)
            else:
                flat_symbols = rnd.get("flat_symbols", [rnd.get("symbol", "X")] * rnd.get("count", 1))

            count = len(flat_symbols)
            if count == 0: continue

            if count == 1:
                xs = [0]
            else:
                xs = np.linspace(-count/2 + 0.5, count/2 - 0.5, count)

            max_x = max(max_x, count/2)

            if count > 1:
                ax.plot([xs[0], xs[-1]], [y, y], color='lightgray', linestyle=':', zorder=1)

            for x, symbol in zip(xs, flat_symbols):
                ax.text(x, y, symbol, ha='center', va='center', fontsize=14, fontweight='bold', zorder=2)

        ax.set_xlim(-max_x - 1, max_x + 1)
        ax.set_ylim(-1, len(rounds) * 1.5)

    return fig

def render_diagram_tool(state_key, key_prefix):
    """共用的動態圖解產生器 UI 模組"""
    if state_key not in st.session_state:
        st.session_state[state_key] = []
    
    builder_key = f"{state_key}_builder"
    if builder_key not in st.session_state:
        st.session_state[builder_key] = []
        
    rounds = st.session_state[state_key]
    
    if len(rounds) == 0:
        col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns(4)
        with col_ctrl1:
            start_type = st.selectbox("起針方式", ["環形起針", "辮子起針"], key=f"{key_prefix}start")
        with col_ctrl2:
            chain_count = 10
            if start_type == "辮子起針":
                chain_count = st.number_input("起針數 (鎖針)", min_value=1, value=10, step=1, key=f"{key_prefix}chain_cnt")
        with col_ctrl3:
            st.write(""); st.write("")
            if st.button("🪄 開始起針", key=f"{key_prefix}btn_start"):
                if start_type == "環形起針":
                    rounds.append({"type": "magic_ring"})
                else:
                    rounds.append({"type": "chain_start", "count": chain_count, "symbol": "CH"})
                st.rerun()
    else:
        st.markdown("##### 🛠️ 手動組合這一圈的針法")
        
        if st.session_state[builder_key]:
            seq_strs = [f"{item['stitch']} x{item['count']}" for item in st.session_state[builder_key]]
            st.info(f"**目前組合：** ( {' + '.join(seq_strs)} )")
        else:
            st.info("請在下方選擇針法並「加入組合」，可加入多種針法")
            
        col_b1, col_b2, col_b3 = st.columns([2, 2, 1])
        with col_b1:
            stitch_type = st.selectbox("新增一種針法", STITCH_OPTIONS, key=f"{key_prefix}stitch")
        with col_b2:
            stitch_count = st.number_input("針數", min_value=1, value=1, step=1, key=f"{key_prefix}cnt")
        with col_b3:
            st.write(""); st.write("")
            if st.button("➕ 加入組合", key=f"{key_prefix}btn_add_seq"):
                symbol_match = re.search(r'[A-Za-z]+', stitch_type)
                symbol = symbol_match.group() if symbol_match else "X"
                st.session_state[builder_key].append({
                    "stitch": stitch_type,
                    "symbol": symbol,
                    "count": stitch_count
                })
                st.rerun()
        
        if st.session_state[builder_key]:
            col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
            with col_r1:
                repeat_times = st.number_input("上述組合重複幾次?", min_value=1, value=1, step=1, key=f"{key_prefix}rep")
            with col_r2:
                st.write(""); st.write("")
                if st.button("✅ 完成並新增這一圈/排", type="primary", key=f"{key_prefix}btn_add_round"):
                    flat_symbols = []
                    total_stitches = 0
                    
                    for _ in range(repeat_times):
                        for item in st.session_state[builder_key]:
                            flat_symbols.extend([item["symbol"]] * item["count"])
                            weight = STITCH_WEIGHTS.get(item["symbol"], 1)
                            total_stitches += weight * item["count"]
                    
                    rounds.append({
                        "type": "round", 
                        "sequence": st.session_state[builder_key].copy(),
                        "repeat": repeat_times,
                        "total_stitches": total_stitches,
                        "flat_symbols": flat_symbols
                    })
                    st.session_state[builder_key] = []
                    st.rerun()
            with col_r3:
                st.write(""); st.write("")
                if st.button("🗑️ 清空組合", key=f"{key_prefix}btn_clear_seq"):
                    st.session_state[builder_key] = []
                    st.rerun()
                    
        st.divider()
        col_reset1, col_reset2 = st.columns([4, 1])
        with col_reset2:
            if st.button("🗑️ 整張圖解重置", key=f"{key_prefix}btn_clear_all"):
                st.session_state[state_key] = []
                st.session_state[builder_key] = []
                st.rerun()

    if len(rounds) > 0:
        st.success(f"目前已完成 {len(rounds) - 1} 圈/排")
        for i, rnd in enumerate(rounds):
            if rnd["type"] == "magic_ring":
                st.caption("起針：環形起針")
            elif rnd["type"] == "chain_start":
                st.caption(f"起針：辮子起針 ({rnd.get('count', 0)} 針)")
            else:
                seq_str = " + ".join([f"{item['symbol']}*{item['count']}" for item in rnd.get("sequence", [])])
                rep = rnd.get("repeat", 1)
                tot = rnd.get("total_stitches", len(rnd.get("flat_symbols", [])))
                if not seq_str:
                    seq_str = f"{rnd.get('symbol', 'X')}*{rnd.get('count', 6)}"
                    rep = 1
                st.caption(f"第 {i} 圈/排：({seq_str}) * {rep} 次 ＝ 共 **{tot}** 針")
        
        fig = draw_diagram(rounds)
        if fig:
            st.pyplot(fig)

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
                image_path TEXT
            )
        ''')
        conn.commit()

init_db()

# --- 側邊欄：導覽列 ---
st.sidebar.title("🧶 AI-Crochet")
page = st.sidebar.radio(
    "請選擇頁面：",
    ["🏠 首頁 - 作品展示", "🧵 材料庫存", "📖 查看織圖", "➕ 新增織圖"]
)
st.sidebar.markdown("---")
st.sidebar.info("歡迎來到你的專屬勾針創作紀錄系統！")

# --- 頁面內容 ---
if page == "🏠 首頁 - 作品展示":
    st.title("🏠 我的勾針作品展示區")
    st.write("這裡是你的作品藝廊！")
    
    with st.expander("➕ 新增完成的作品到展示區"):
        with st.form("add_project_form", clear_on_submit=True):
            proj_name = st.text_input("作品名稱 *")
            proj_desc = st.text_area("作品描述 / 心得")
            proj_image = st.file_uploader("上傳作品照片", type=["jpg", "png", "jpeg"])
            
            if st.form_submit_button("新增作品"):
                if proj_name and proj_image:
                    file_path = os.path.join(UPLOAD_DIR, proj_image.name)
                    with open(file_path, "wb") as f:
                        f.write(proj_image.getbuffer())
                    
                    with get_connection() as conn:
                        c = conn.cursor()
                        c.execute("INSERT INTO projects (name, description, image_path) VALUES (?, ?, ?)",
                                  (proj_name, proj_desc, file_path))
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
                            new_image = st.file_uploader("更換照片 (若不更換請留白)", type=["jpg", "png", "jpeg"])
                            
                            if st.form_submit_button("💾 儲存修改", use_container_width=True):
                                update_path = row['image_path']
                                if new_image:
                                    update_path = os.path.join(UPLOAD_DIR, new_image.name)
                                    with open(update_path, "wb") as f:
                                        f.write(new_image.getbuffer())
                                        
                                with get_connection() as conn:
                                    c = conn.cursor()
                                    c.execute("UPDATE projects SET name=?, description=?, image_path=? WHERE id=?",
                                              (new_name, new_desc, update_path, row['id']))
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
            
            if "edit_gen_rounds" not in st.session_state:
                if row.get('diagram_data') and row['diagram_data']:
                    try: st.session_state.edit_gen_rounds = json.loads(row['diagram_data'])
                    except: st.session_state.edit_gen_rounds = []
                else: st.session_state.edit_gen_rounds = []

            new_name = st.text_input("織圖名稱 *", value=row['name'])
            types = ["玩偶 (Amigurumi)", "服飾", "包包", "家飾", "其他"]
            type_idx = types.index(row['type']) if row['type'] in types else 0
            new_type = st.selectbox("分類", types, index=type_idx)
            
            col1, col2 = st.columns(2)
            with col1:
                new_yarn = st.text_input("建議線材", value=row['yarn_req'] if row['yarn_req'] else "")
            with col2:
                new_hook = st.text_input("建議勾針尺寸", value=row['hook_size'] if row['hook_size'] else "")
                
            new_file = st.file_uploader("更換織圖檔案 (若不更換請留白)", type=["jpg", "png", "jpeg", "pdf"])
            new_notes = st.text_area("整體筆記 / 心得", value=row['notes'] if row['notes'] else "")
            
            st.divider()

            if "edit_pattern_sections" not in st.session_state:
                if row['sections_data']:
                    try:
                        loaded_sections = json.loads(row['sections_data'])
                        for sec in loaded_sections:
                            sec['data'] = pd.DataFrame(sec['data'])
                        st.session_state.edit_pattern_sections = loaded_sections
                    except Exception:
                        st.session_state.edit_pattern_sections = [{"name": "區段 1", "data": pd.DataFrame([{"圈數": "1", "針法": "", "針數": "", "備註": ""}])}]
                else:
                    st.session_state.edit_pattern_sections = [{"name": "區段 1", "data": pd.DataFrame([{"圈數": "1", "針法": "", "針數": "", "備註": ""}])}]
            
            # --- 【位置調換】織法表格移至上方 ---
            st.subheader("📝 編輯織法表格")
            sections_to_remove = []
            needs_rerun = False
            for i, sec in enumerate(st.session_state.edit_pattern_sections):
                scol1, scol2 = st.columns([4, 1])
                with scol1:
                    sec['name'] = st.text_input("區段名稱", value=sec['name'], key=f"edit_sec_name_{i}")
                with scol2:
                    st.write(""); st.write("")
                    if st.button("🗑️ 刪除區段", key=f"edit_del_sec_{i}"):
                        sections_to_remove.append(i)
                        
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
                
                # --- 強化：不管新增或刪除，全面強制由上往下重算圈數 ---
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
                    
                with st.expander("🛠️ 使用組合建構器新增一圈", expanded=False):
                    if st.session_state[builder_key]:
                        seq_strs = [f"{item['stitch']} x{item['count']}" for item in st.session_state[builder_key]]
                        st.info(f"**目前組合：** ( {' + '.join(seq_strs)} )")
                        
                    col_b1, col_b2, col_b3 = st.columns([2, 2, 1])
                    with col_b1: stitch_type = st.selectbox("新增一種針法", STITCH_OPTIONS, key=f"edit_b_stitch_{i}")
                    with col_b2: stitch_count = st.number_input("針數", min_value=1, value=1, step=1, key=f"edit_b_cnt_{i}")
                    with col_b3:
                        st.write(""); st.write("")
                        if st.button("➕ 加入組合", key=f"edit_b_add_{i}"):
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
                for idx in sorted(sections_to_remove, reverse=True):
                    st.session_state.edit_pattern_sections.pop(idx)
                st.rerun()
            elif needs_rerun:
                st.rerun()
                
            if st.button("➕ 新增下一個區段"):
                new_idx = len(st.session_state.edit_pattern_sections) + 1
                st.session_state.edit_pattern_sections.append({
                    "name": f"區段 {new_idx}",
                    "data": pd.DataFrame([{"圈數": "1", "針法": "", "針數": "", "備註": ""}])
                })
                st.rerun()
                
            st.divider()

            # --- 【位置調換】自動化圖解移至下方 ---
            with st.expander("🪄 編輯自動化圖解 (由表格產生)", expanded=True):
                if st.button("🔄 一鍵將上方表格資料匯入織圖產生器", type="primary", use_container_width=True, key="edit_sync_btn"):
                    new_rounds = []
                    is_first_row = True
                    for sec in st.session_state.edit_pattern_sections:
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
                                    
                            new_rounds.append({"type": "round", "flat_symbols": flat_syms, "count": len(flat_syms)})
                    st.session_state.edit_gen_rounds = new_rounds
                    st.success("✅ 圖解資料轉換成功！")
                    st.rerun()

                st.write("---")
                render_diagram_tool("edit_gen_rounds", "edit_diag_")
                
            st.divider()
            
            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.button("💾 儲存修改", type="primary", use_container_width=True):
                    if new_name:
                        update_path = row['file_path']
                        if new_file is not None:
                            update_path = os.path.join(UPLOAD_DIR, new_file.name)
                            with open(update_path, "wb") as f:
                                f.write(new_file.getbuffer())
                                
                        save_data = []
                        for sec in st.session_state.edit_pattern_sections:
                            save_data.append({
                                "name": sec['name'],
                                "data": sec['data'].to_dict(orient="records")
                            })
                        sections_json = json.dumps(save_data, ensure_ascii=False)
                        diagram_json = json.dumps(st.session_state.edit_gen_rounds, ensure_ascii=False)
                        
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
                        if "edit_gen_rounds" in st.session_state: del st.session_state.edit_gen_rounds
                        st.rerun()
                    else:
                        st.error("請填寫織圖名稱！")
                        
            with col_cancel:
                if st.button("❌ 取消編輯", use_container_width=True):
                    st.session_state.edit_pattern_id = None
                    if "edit_pattern_sections" in st.session_state: del st.session_state.edit_pattern_sections
                    if "edit_gen_rounds" in st.session_state: del st.session_state.edit_gen_rounds
                    st.rerun()

    else:
        # === 模式 A：織圖列表瀏覽模式 ===
        st.title("📖 織圖庫")
        st.write("你收藏與紀錄的所有織圖都在這裡。")
        
        search_query = st.text_input("🔍 搜尋織圖名稱或分類...")
        with get_connection() as conn:
            if search_query:
                query = f"SELECT * FROM patterns WHERE name LIKE '%{search_query}%' OR type LIKE '%{search_query}%'"
                patterns_df = pd.read_sql(query, conn)
            else:
                patterns_df = pd.read_sql("SELECT * FROM patterns", conn)
                
        if patterns_df.empty:
            st.info("找不到符合的織圖。")
        else:
            for index, row in patterns_df.iterrows():
                with st.expander(f"🌸 {row['name']} ({row['type']})"):
                    st.write(f"**建議線材：** {row['yarn_req']}")
                    st.write(f"**建議勾針：** {row['hook_size']}")
                    st.write(f"**整體筆記：** {row['notes']}")
                    
                    if row.get('diagram_data') and row['diagram_data']:
                        try:
                            diag_data = json.loads(row['diagram_data'])
                            if diag_data:
                                st.divider()
                                st.markdown("#### 🪄 圖解預覽")
                                fig = draw_diagram(diag_data)
                                if fig:
                                    st.pyplot(fig)
                        except Exception:
                            pass
                    
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
                        except Exception as e:
                            st.error(f"無法解析表格資料: {e}")
                    
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
    with col1:
        yarn_req = st.text_input("建議線材", key="p_yarn")
    with col2:
        hook_size = st.text_input("建議勾針尺寸 (例如: 3.0mm, 5/0)", key="p_hook")
        
    uploaded_file = st.file_uploader("上傳織圖檔案 (圖片或 PDF)", type=["jpg", "png", "jpeg", "pdf"], key="p_file")
    notes = st.text_area("整體筆記 / 心得", key="p_notes")
    
    st.divider()
    
    # --- 【位置調換】織法表格移至上方 ---
    st.subheader("📝 織法表格 (支援多區段)")
    st.info("💡 提示：若刪除中間的圈數，後續的編號將自動向前遞補喔！")
    
    sections_to_remove = []
    needs_rerun = False
    for i, sec in enumerate(st.session_state.pattern_sections):
        scol1, scol2 = st.columns([4, 1])
        with scol1:
            sec['name'] = st.text_input("區段名稱", value=sec['name'], key=f"sec_name_{i}")
        with scol2:
            st.write(""); st.write("")
            if st.button("🗑️ 刪除區段", key=f"del_sec_{i}"):
                sections_to_remove.append(i)
                
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
        
        # --- 強化：不管新增或刪除，全面強制由上往下重算圈數 ---
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
            
        with st.expander("🛠️ 使用組合建構器新增一圈", expanded=True):
            if st.session_state[builder_key]:
                seq_strs = [f"{item['stitch']} x{item['count']}" for item in st.session_state[builder_key]]
                st.info(f"**目前組合：** ( {' + '.join(seq_strs)} )")
                
            col_b1, col_b2, col_b3 = st.columns([2, 2, 1])
            with col_b1: stitch_type = st.selectbox("新增一種針法", STITCH_OPTIONS, key=f"b_stitch_{i}")
            with col_b2: stitch_count = st.number_input("針數", min_value=1, value=1, step=1, key=f"b_cnt_{i}")
            with col_b3:
                st.write(""); st.write("")
                if st.button("➕ 加入組合", key=f"b_add_{i}"):
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
        for idx in sorted(sections_to_remove, reverse=True):
            st.session_state.pattern_sections.pop(idx)
        st.rerun()
    elif needs_rerun:
        st.rerun()
        
    if st.button("➕ 新增下一個區段 (例如：手、身體)"):
        new_idx = len(st.session_state.pattern_sections) + 1
        st.session_state.pattern_sections.append({
            "name": f"區段 {new_idx}",
            "data": pd.DataFrame([{"圈數": "1", "針法": "", "針數": "", "備註": ""}])
        })
        st.rerun()
        
    st.divider()

    # --- 【位置調換】自動化圖解移至下方 ---
    with st.expander("🪄 自動化織圖產生器 (由表格產生)", expanded=True):
        st.write("在上方表格完成編輯後，點擊下方按鈕即可一鍵繪製圖解！")
        
        # 【黑科技】一鍵匯入按鈕
        if st.button("🔄 一鍵將上方表格資料匯入織圖產生器", type="primary", use_container_width=True, key="add_sync_btn"):
            new_rounds = []
            is_first_row = True
            for sec in st.session_state.pattern_sections:
                for _, r in sec['data'].iterrows():
                    stitch_str = str(r['針法'])
                    flat_syms = parse_stitch_string(stitch_str)
                    if not flat_syms: continue
                    
                    if is_first_row:
                        is_first_row = False
                        # 簡單判斷：如果第一圈有出現 "CH" 或 "鎖" 字眼，就視為平織辮子起針
                        if "CH" in stitch_str.upper() or "鎖" in stitch_str:
                            new_rounds.append({"type": "chain_start", "count": len(flat_syms), "symbol": "CH"})
                            continue # 起針本身就是一列，不需再當作一般圈數加入
                        else:
                            new_rounds.append({"type": "magic_ring"})
                            
                    new_rounds.append({"type": "round", "flat_symbols": flat_syms, "count": len(flat_syms)})
                    
            st.session_state.gen_rounds = new_rounds
            st.success("✅ 圖解資料轉換成功！")
            st.rerun()

        st.write("---")
        render_diagram_tool("gen_rounds", "add_diag_")

    st.divider()
    
    if st.button("💾 儲存完整織圖", type="primary", use_container_width=True):
        if pattern_name:
            file_path = ""
            if uploaded_file is not None:
                file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
            
            save_data = []
            for sec in st.session_state.pattern_sections:
                save_data.append({
                    "name": sec['name'],
                    "data": sec['data'].to_dict(orient="records")
                })
            sections_json = json.dumps(save_data, ensure_ascii=False)
            diagram_json = json.dumps(st.session_state.get("gen_rounds", []), ensure_ascii=False)
            
            with get_connection() as conn:
                c = conn.cursor()
                c.execute('''INSERT INTO patterns 
                             (name, type, yarn_req, hook_size, notes, file_path, sections_data, diagram_data) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                          (pattern_name, pattern_type, yarn_req, hook_size, notes, file_path, sections_json, diagram_json))
                conn.commit()
            
            st.success(f"✅ 成功新增織圖：{pattern_name}！請至「查看織圖」頁面確認。")
            
            del st.session_state.pattern_sections
            if "gen_rounds" in st.session_state: del st.session_state.gen_rounds
            for key in ["p_name", "p_yarn", "p_hook", "p_notes"]:
                if key in st.session_state: st.session_state[key] = ""
            st.rerun()
        else:
            st.error("請填寫織圖名稱！")