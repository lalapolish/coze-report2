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
# 核心逻辑：按章节划分的函数处理区
# =================================================================

# ----------------- 【第 2 章：发文规模】 -----------------
# 依赖：科研论文.xlsx
def get_chapter_2_data(df, target_years):
    # 年度趋势统计
    trend = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    # 学院排名统计
    valid_df = df[df['发表年份'].isin(target_years)]
    unit_table = pd.pivot_table(valid_df, index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    unit_table = unit_table.reset_index()
    
    # 过滤教学科研单位
    valid_pattern = '学院|学部|图书馆|研究院|中心'
    unit_table = unit_table[unit_table['所属单位'].str.contains(valid_pattern, na=False)]
    
    unit_table['total'] = unit_table[target_years].sum(axis=1)
    unit_table = unit_table.sort_values(by='total', ascending=False)
    unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
    
    mapping = {'所属单位': 'unit_name', 2020: 'year_2020', 2021: 'year_2021', 2022: 'year_2022', 2023: 'year_2023', 2024: 'year_2024'}
    unit_table = unit_table.rename(columns=mapping)
    
    return {
        "table_1_trend": trend.to_dict(orient='records'),
        "table_2_unit": unit_table[['id', 'unit_name', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']].to_dict(orient='records')
    }

# ----------------- 【第 3 章：发文期刊】 -----------------
# ----------------- (逻辑待补充，暂用注释隔断) -----------------
def get_chapter_3_data(df, target_years):
    # TODO: 待后续提供作图逻辑后补全
    return {"message": "第 3 章逻辑待开发"}
# ---------------------------------------------------------

# ----------------- 【第 4 章：基金项目】 -----------------
# 依赖：基金项目.xlsx (包含纵向和横向两个 Sheet)
def get_chapter_4_data(df_long, df_horiz, target_years):
    # 内部日期解析助手
    def parse_year(df, date_col, year_col):
        if date_col in df.columns:
            return pd.to_datetime(df[date_col].astype(str).str.replace('.', '-', regex=False), errors='coerce').dt.year
        return df[year_col] if year_col in df.columns else None

    df_long['year'] = parse_year(df_long, '立项日期', '立项年份')
    df_horiz['year'] = parse_year(df_horiz, '立项日期', '立项年份')
    
    long_v = df_long[df_long['year'].isin(target_years)].copy()
    horiz_v = df_horiz[df_horiz['year'].isin(target_years)].copy()

    # --- 纵向项目部分 ---
    # 图 1：立项年份分布
    trend_long = long_v.groupby('year').size().reindex(target_years, fill_value=0).reset_index()
    trend_long.columns = ['year', 'count']

    # 图 2：项目级别分布
    level_dist = long_v['项目级别'].value_counts().reset_index()
    level_dist.columns = ['level', 'count']
    level_dist['ratio'] = (level_dist['count'] / level_dist['count'].sum() * 100).round(2).astype(str) + '%'

    # 表 1：立项年份分布（国家级和省部级）
    t1_pivot = pd.pivot_table(long_v, index='year', columns='项目级别', aggfunc='size', fill_value=0)
    for c in ['国家级', '省部级']: 
        if c not in t1_pivot.columns: t1_pivot[c] = 0
    t1 = t1_pivot[['国家级', '省部级']].reindex(target_years, fill_value=0).reset_index()
    t1['总计'] = t1['国家级'] + t1['省部级']
    summary_1 = pd.DataFrame([['总计', t1['国家级'].sum(), t1['省部级'].sum(), t1['总计'].sum()]], columns=['year','国家级','省部级','总计'])
    t1_final = pd.concat([t1, summary_1])

    # 表 2：所属单位统计（前24）
    t2_pivot = pd.pivot_table(long_v[long_v['归属单位'].notna()], index='归属单位', columns='year', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in t2_pivot.columns: t2_pivot[y] = 0
    t2_pivot['total'] = t2_pivot.sum(axis=1)
    t2_table = t2_pivot.sort_values('total', ascending=False).head(24).reset_index()
    t2_table.insert(0, '序号', range(1, len(t2_table) + 1))

    # 图 3：学校认定等级
    rank_dist = long_v['学校等级认定'].value_counts().reset_index()
    rank_dist.columns = ['rank', 'count']
    rank_dist['ratio'] = (rank_dist['count'] / rank_dist['count'].sum() * 100).round(2).astype(str) + '%'

    # 图 4：经费区间 (0-20, 20-40...)
    bins = [0, 20, 40, 60, 80, 100, 120]
    labels = ['(0-20)', '[20-40)', '[40-60)', '[60-80)', '[80-100)', '[100-120]']
    long_v['range'] = pd.cut(long_v['立项经费(万元)'], bins=bins, labels=labels, right=False)
    long_money_dist = long_v['range'].value_counts().reindex(labels, fill_value=0).reset_index()

    # 表 3：立项经费 Top10 数量
    top10_money = long_v['立项经费(万元)'].value_counts().head(10).reset_index()
    top10_money.columns = ['经费额', '项目数量']
    top10_money['占比'] = (top10_money['项目数量'] / len(long_v) * 100).round(2).astype(str) + '%'

    # 表 4：经费额度统计
    t4_pivot = pd.pivot_table(long_v, index='year', columns='项目级别', values='立项经费(万元)', aggfunc='sum', fill_value=0)
    cols4 = ['国际（地区）合作', '国家级', '省部级', '厅局级']
    for c in cols4:
        if c not in t4_pivot.columns: t4_pivot[c] = 0
    t4 = t4_pivot[cols4].reindex(target_years, fill_value=0).reset_index()
    t4['总计（万）'] = t4[cols4].sum(axis=1)
    summary_4 = pd.DataFrame([['总计（万）'] + [t4[c].sum().round(1) for c in cols4 + ['总计（万）']]], columns=['year'] + cols4 + ['总计（万）'])
    t4_final = pd.concat([t4, summary_4]).round(1)

    # --- 横向项目部分 ---
    # 图 4(横)：立项年份
    trend_horiz = horiz_v.groupby('year').size().reindex(target_years, fill_value=0).reset_index()
    
    # 表 5：所属单位统计（前19，带清洗）
    horiz_v['归属单位'] = horiz_v['归属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())
    h_unit_pivot = pd.pivot_table(horiz_v[horiz_v['归属单位'].str.contains('学院|学部|图书馆|研究院|中心', na=False)], 
                                  index='归属单位', columns='year', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in h_unit_pivot.columns: h_unit_pivot[y] = 0
    h_unit_pivot['total'] = h_unit_pivot.sum(axis=1)
    h_unit_table = h_unit_pivot.sort_values('total', ascending=False).head(19).reset_index()

    # 图 5：横向到账经费区间
    h_bins = [0, 5, 10, 20, 30, 50, 100, 200, 600]
    h_labels = ['(0-5)', '[5-10)', '[10-20)', '[20-30)', '[30-50)', '[50-100)', '[100-200)', '[200-600)']
    horiz_v['range'] = pd.cut(horiz_v['到账经费'], bins=h_bins, labels=h_labels, right=False)
    horiz_money_dist = horiz_v['range'].value_counts().reindex(h_labels, fill_value=0).reset_index()

    # 表 6：到账经费 Top9
    top9_income = horiz_v['到账经费'].value_counts().head(9).reset_index()
    top9_income.columns = ['经费额', '项目数量']
    top9_income['占比'] = (top9_income['项目数量'] / len(horiz_v) * 100).round(2).astype(str) + '%'

    # 图 6：趋势混合图
    trend_mix = horiz_v.groupby('year').agg({'WID': 'count', '到账经费': 'sum'}).reindex(target_years, fill_value=0).reset_index()

    return {
        "longitudinal": {
            "chart_1": trend_long.to_dict(orient='records'),
            "chart_2": level_dist.to_dict(orient='records'),
            "table_1": t1_final.to_dict(orient='records'),
            "table_2": t2_table.to_dict(orient='records'),
            "chart_3": rank_dist.to_dict(orient='records'),
            "chart_4": long_money_dist.to_dict(orient='records'),
            "table_3": top10_money.to_dict(orient='records'),
            "table_4": t4_final.to_dict(orient='records')
        },
        "horizontal": {
            "chart_4": trend_horiz.to_dict(orient='records'),
            "table_5": h_unit_table.to_dict(orient='records'),
            "chart_5": horiz_money_dist.to_dict(orient='records'),
            "table_6": top9_income.to_dict(orient='records'),
            "chart_6": trend_mix.to_dict(orient='records')
        }
    }

# ----------------- 【第 5 章：重要学者】 -----------------
# ----------------- (逻辑待补充，暂用注释隔断) -----------------
def get_chapter_5_data(df, target_years):
    # TODO: 待后续提供作图逻辑后补全
    return {"message": "第 5 章逻辑待开发"}
# ---------------------------------------------------------

# ----------------- 【第 6 章：专著】 -----------------
def get_chapter_6_data(df, target_years):
    trend = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    unit_table = pd.pivot_table(df[df['发表年份'].isin(target_years)], index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    unit_table = unit_table.reset_index()
    unit_table = unit_table[unit_table['所属单位'].str.contains('学院|学部|图书馆|研究院|中心', na=False)]
    unit_table['total'] = unit_table[target_years].sum(axis=1)
    unit_table = unit_table.sort_values(by='total', ascending=False)
    unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
    
    return {
        "table_1_trend": trend.to_dict(orient='records'),
        "table_2_unit": unit_table.to_dict(orient='records')
    }

# ----------------- 【第 7 章：获奖情况】 -----------------
def get_chapter_7_data(df, target_years):
    # 图 1：趋势
    trend = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    # 图 2：等级分布 (清洗逻辑)
    def normalize_level(x):
        x = str(x).strip().upper()
        for letter in ['A', 'B', 'C', 'D', 'E', 'F']:
            if letter in x: return f"{letter}级"
        return '其他'

    valid_df = df[df['发表年份'].isin(target_years)].copy()
    valid_df['等级'] = valid_df['学校认定等级'].apply(normalize_level)
    
    dist_table = pd.pivot_table(valid_df, index='发表年份', columns='等级', aggfunc='size', fill_value=0)
    levels = ['A级', 'B级', 'C级', 'D级', 'E级', 'F级']
    for lv in levels:
        if lv not in dist_table.columns: dist_table[lv] = 0
    
    dist_table = dist_table.reindex(target_years, fill_value=0).reset_index()
    return {
        "table_1_trend": trend.to_dict(orient='records'),
        "table_2_level_dist": dist_table.to_dict(orient='records')
    }


# =================================================================
# 主接口：负责文件识别与任务分拣
# =================================================================

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        file_name = unquote(input.file_url.split('/')[-1])
        response = requests.get(input.file_url)
        content = io.BytesIO(response.content)
        target_years = [2020, 2021, 2022, 2023, 2024]

        # 1. 识别：基金项目（双 Sheet）
        if "项目" in file_name or "课题" in file_name:
            sheets = pd.read_excel(content, sheet_name=None)
            s_names = list(sheets.keys())
            df_long = sheets[s_names[0]]
            df_horiz = sheets[s_names[1]] if len(s_names) > 1 else pd.DataFrame()
            return {"status": "success", "data": {"chapter_4": get_chapter_4_data(df_long, df_horiz, target_years)}}

        # 2. 识别：单表（论文/专著/获奖）
        df = pd.read_excel(content, sheet_name=0)
        df.columns = df.columns.str.strip()

        # 统一日期预处理
        if '获奖日期' in df.columns:
            df['发表年份'] = pd.to_datetime(df['获奖日期'], errors='coerce').dt.year
        elif '出版时间' in df.columns:
            df['发表年份'] = pd.to_datetime(df['出版时间'], errors='coerce').dt.year
        elif '发表年份' in df.columns:
            df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')

        if '所属单位' in df.columns:
            df['所属单位'] = df['所属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())

        result_data = {}
        if "论文" in file_name:
            result_data["chapter_2"] = get_chapter_2_data(df, target_years)
            result_data["chapter_3"] = get_chapter_3_data(df, target_years)
        elif "专著" in file_name:
            result_data["chapter_6"] = get_chapter_6_data(df, target_years)
        elif "获奖" in file_name:
            result_data["chapter_7"] = get_chapter_7_data(df, target_years)
        else:
            return {"status": "warning", "message": f"文件名 [{file_name}] 未匹配到业务表"}

        return {"status": "success", "data": result_data}

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
