from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import numpy as np
import io
import requests
from urllib.parse import unquote
import traceback

app = FastAPI(openapi_version="3.0.2")

class FileInput(BaseModel):
    file_url: str 

# =================================================================
# 1. 通用辅助工具函数
# =================================================================

def parse_project_year(df, date_col, year_col):
    """兼容处理项目表的日期格式（支持 2021.10.01 或 2021 等）"""
    if date_col in df.columns:
        return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
    return df[year_col] if year_col in df.columns else None

def clean_unit_name(name):
    """清洗单位名称：去除括号及内部行政后缀，保留核心学院名"""
    return str(name).split('（')[0].split('(')[0].strip()

# =================================================================
# 2. 章节逻辑计算函数
# =================================================================

def get_chapter_2_data(df, target_years):
    temp_df = df.copy()
    temp_df['所属单位'] = temp_df['所属单位'].apply(clean_unit_name)
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index(name='count')
    
    valid_df = temp_df[temp_df['发表年份'].isin(target_years)]
    unit_table = pd.pivot_table(valid_df, index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    unit_table = unit_table.reset_index()
    unit_table = unit_table[unit_table['所属单位'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    unit_table['total'] = unit_table[target_years].sum(axis=1)
    unit_table = unit_table.sort_values(by='total', ascending=False)
    unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
    return {"table_1_trend": trend.to_dict(orient='records'), "table_2_unit": unit_table.to_dict(orient='records')}

def get_chapter_3_data(df, target_years):
    temp_df = df.copy()
    temp_df['所属单位'] = temp_df['所属单位'].apply(clean_unit_name)
    def clean_level(x):
        x = str(x).upper()
        for lv in ['B', 'C', 'D', 'E', 'F']:
            if lv in x: return f"{lv}级"
        return "其他"
    v3_df = temp_df[temp_df['发表年份'].isin(target_years)].copy()
    v3_df['等级'] = v3_df['学校认定等级'].apply(clean_level)
    target_levels = ['B级', 'C级', 'D级', 'E级', 'F级']
    chart1 = pd.pivot_table(v3_df, index='发表年份', columns='等级', aggfunc='size', fill_value=0)
    for lv in target_levels:
        if lv not in chart1.columns: chart1[lv] = 0
    chart1 = chart1[target_levels].reindex(target_years, fill_value=0).reset_index()
    
    v3_unit_df = v3_df[v3_df['所属单位'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    table1 = pd.pivot_table(v3_unit_df, index='所属单位', columns='等级', aggfunc='size', fill_value=0)
    for lv in target_levels:
        if lv not in table1.columns: table1[lv] = 0
    table1 = table1[target_levels].copy()
    table1['总计'] = table1.sum(axis=1)
    table1 = table1.sort_values('总计', ascending=False).reset_index()
    return {"chart_1_level_year": chart1.to_dict(orient='records'), "table_1_unit_level": table1.head(10).to_dict(orient='records')}

def get_chapter_4_data(df_long, df_horiz, target_years):
    # 纵向分析
    df_long['year'] = parse_project_year(df_long, '立项日期', '立项年份')
    long_v = df_long[df_long['year'].isin(target_years)].copy()
    trend_long = long_v.groupby('year').size().reindex(target_years, fill_value=0).reset_index(name='count')
    level_dist = long_v['项目级别'].value_counts().reset_index().rename(columns={'index':'level','项目级别':'count'})
    
    # 横向分析
    horiz_res = {}
    if not df_horiz.empty:
        df_horiz['year'] = parse_project_year(df_horiz, '立项日期', '立项年份')
        horiz_v = df_horiz[df_horiz['year'].isin(target_years)].copy()
        trend_horiz = horiz_v.groupby('year').size().reindex(target_years, fill_value=0).reset_index(name='count')
        horiz_res = {"trend": trend_horiz.to_dict(orient='records')}

    return {"longitudinal": {"trend": trend_long.to_dict(orient='records'), "level_dist": level_dist.to_dict(orient='records')}, "horizontal": horiz_res}

def get_chapter_5_paper_part(df, target_years):
    v5_df = df[df['发表年份'].isin(target_years)].copy()
    def clean_level(x):
        x = str(x).upper()
        for lv in ['B', 'C', 'D', 'E', 'F']:
            if lv in x: return f"{lv}级"
        return "其他"
    v5_df['等级'] = v5_df['学校认定等级'].apply(clean_level)
    paper_stats = pd.pivot_table(v5_df, index=['作者姓名', '所属单位'], columns='等级', aggfunc='size', fill_value=0)
    for lv in ['B级', 'C级', 'D级', 'E级', 'F级']:
        if lv not in paper_stats.columns: paper_stats[lv] = 0
    paper_stats['总计'] = paper_stats.sum(axis=1)
    
    table_1 = paper_stats[paper_stats['总计'] >= 15].sort_values('总计', ascending=False).reset_index()
    b_list = paper_stats[paper_stats['B级'] >= 4].sort_values('B级', ascending=False).reset_index()[['作者姓名', 'B级', '所属单位']]
    c_list = paper_stats[paper_stats['C级'] >= 4].sort_values('C级', ascending=False).reset_index()[['作者姓名', 'C级', '所属单位']]
    
    return {
        "table_1_total_ge_15": table_1.to_dict(orient='records'),
        "table_2_high_level": {
            "B_level_ge_4": b_list.rename(columns={'B级': '发文数量'}).to_dict(orient='records'),
            "C_level_ge_4": c_list.rename(columns={'C级': '发文数量'}).to_dict(orient='records')
        }
    }

def get_chapter_5_project_part(df_long, df_horiz, target_years):
    df_long['year'] = parse_project_year(df_long, '立项日期', '立项年份')
    long_v = df_long[df_long['year'].isin(target_years)].copy()
    v_stats = long_v.groupby('负责人').size().reset_index(name='立项数量').sort_values('立项数量', ascending=False)
    
    h_res = {}
    if not df_horiz.empty:
        df_horiz['year'] = parse_project_year(df_horiz, '立项日期', '立项年份')
        horiz_v = df_horiz[df_horiz['year'].isin(target_years)].copy()
        h_stats = horiz_v.groupby('项目负责人').size().reset_index(name='立项数量').sort_values('立项数量', ascending=False)
        h_res = {"top_scholars": h_stats[h_stats['立项数量'] >= 5].to_dict(orient='records')}

    return {"vertical_stats": v_stats[v_stats['立项数量'] >= 5].to_dict(orient='records'), "horizontal_stats": h_res}

def get_chapter_6_data(df, target_years):
    temp_df = df.copy()
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index(name='count')
    return {"trend": trend.to_dict(orient='records')}

def get_chapter_7_data(df, target_years):
    temp_df = df.copy()
    trend = temp_df[temp_df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index(name='count')
    return {"trend": trend.to_dict(orient='records')}


# =================================================================
# 3. 主接口：Sheet 识别与顺序重组
# =================================================================

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        response = requests.get(input.file_url)
        content = io.BytesIO(response.content)
        all_sheets = pd.read_excel(content, sheet_name=None)
        
        target_years = [2020, 2021, 2022, 2023, 2024]
        raw_outputs = {}

        # --- 第一步：根据 Sheet 存在情况计算原始数据 ---
        
        if "科研论文" in all_sheets:
            df_p = all_sheets["科研论文"]
            df_p.columns = df_p.columns.str.strip()
            df_p['发表年份'] = pd.to_numeric(df_p['发表年份'], errors='coerce')
            raw_outputs["c2"] = get_chapter_2_data(df_p, target_years)
            raw_outputs["c3"] = get_chapter_3_data(df_p, target_years)
            raw_outputs["c5_paper"] = get_chapter_5_paper_part(df_p, target_years)

        if "纵向项目" in all_sheets:
            df_long = all_sheets["纵向项目"]
            df_horiz = all_sheets.get("横向项目", pd.DataFrame())
            raw_outputs["c4"] = get_chapter_4_data(df_long, df_horiz, target_years)
            raw_outputs["c5_project"] = get_chapter_5_project_part(df_long, df_horiz, target_years)

        if "专著" in all_sheets:
            df_b = all_sheets["专著"]
            df_b['发表年份'] = pd.to_datetime(df_b['出版时间'], errors='coerce').dt.year
            raw_outputs["c6"] = get_chapter_6_data(df_b, target_years)

        if "获奖" in all_sheets:
            df_a = all_sheets["获奖"]
            df_a['发表年份'] = pd.to_datetime(df_a['获奖日期'], errors='coerce').dt.year
            raw_outputs["c7"] = get_chapter_7_data(df_a, target_years)

        # --- 第二步：核心逻辑——强制执行章节顺序重组 ---
        
        final_ordered_data = {}
        
        # 严格按 2->3->4->5->6->7 顺序填充
        if "c2" in raw_outputs: final_ordered_data["chapter_2_scale"] = raw_outputs["c2"]
        if "c3" in raw_outputs: final_ordered_data["chapter_3_journals"] = raw_outputs["c3"]
        if "c4" in raw_outputs: final_ordered_data["chapter_4_projects"] = raw_outputs["c4"]
        
        # 深度整合第 5 章
        if "c5_paper" in raw_outputs or "c5_project" in raw_outputs:
            final_ordered_data["chapter_5_scholars"] = {
                "paper_analysis": raw_outputs.get("c5_paper"),
                "project_analysis": raw_outputs.get("c5_project")
            }
            
        if "c6" in raw_outputs: final_ordered_data["chapter_6_monographs"] = raw_outputs["c6"]
        if "c7" in raw_outputs: final_ordered_data["chapter_7_awards"] = raw_outputs["c7"]

        return {
            "status": "success",
            "data": final_ordered_data
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
