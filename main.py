from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
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
# 依赖：表 1（科研论文）
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
# 依赖：表 1（科研论文）
def get_chapter_3_data(df, target_years):
    # TODO: 待补充作图逻辑
    return {"message": "第 3 章逻辑待开发"}

# ----------------- 【第 4 章：基金课题】 -----------------
# 依赖：表 2（基金项目）
def get_chapter_4_data(df, target_years):
    # TODO: 待补充作图逻辑
    return {"message": "第 4 章逻辑待开发"}

# ----------------- 【第 5 章：重要学者】 -----------------
# 综合依赖：表 1（科研论文）和 表 2（基金项目）
def get_chapter_5_data(df, target_years):
    # TODO: 待补充多表综合逻辑
    return {"message": "第 5 章逻辑待开发"}

# ----------------- 【第 6 章：专著】 -----------------
# 依赖：表 3（专著）
def get_chapter_6_data(df, target_years):
    # 统计逻辑（同第 2 章规模分析，但作用于专著数据）
    trend = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
    trend = trend.reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    
    unit_table = pd.pivot_table(df[df['发表年份'].isin(target_years)], index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    unit_table = unit_table.reset_index()
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

# ----------------- 【第 7 章：获奖情况】 -----------------
# 依赖：表 4（科研获奖）
def get_chapter_7_data(df, target_years):
    # TODO: 待补充作图逻辑
    return {"message": "第 7 章逻辑待开发"}


# =================================================================
# 主接口：负责文件识别与任务分拣
# =================================================================

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        # 1. 获取并解码文件名
        file_name = unquote(input.file_url.split('/')[-1])
        
        # 2. 读取数据
        response = requests.get(input.file_url)
        df = pd.read_excel(io.BytesIO(response.content), sheet_name=0)
        df.columns = df.columns.str.strip()

        # 3. 预处理：根据不同表头统一“年份”字段
        if '出版时间' in df.columns: # 专著表
            df['发表年份'] = pd.to_datetime(df['出版时间'], errors='coerce').dt.year
        elif '发表年份' in df.columns: # 论文表
            df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        elif '批准年份' in df.columns: # 项目表
            df['发表年份'] = pd.to_numeric(df['批准年份'], errors='coerce')
        elif '获奖年份' in df.columns: # 获奖表
            df['发表年份'] = pd.to_numeric(df['获奖年份'], errors='coerce')

        # 4. 预处理：所属单位清洗
        if '所属单位' in df.columns:
            df['所属单位'] = df['所属单位'].apply(lambda x: str(x).split('（')[0].split('(')[0].strip())

        target_years = [2020, 2021, 2022, 2023, 2024]
        result_data = {}

        # ---------------------------------------------------------
        # 分路识别：根据文件名决定调用哪些章节函数
        # ---------------------------------------------------------
        
        # 匹配 表 1：科研论文 -> 处理第 2、3、5 章
        if "论文" in file_name:
            result_data["chapter_2"] = get_chapter_2_data(df, target_years)
            result_data["chapter_3"] = get_chapter_3_data(df, target_years)
            result_data["chapter_5_partial"] = "论文部分数据已加载，待项目数据合并"

        # 匹配 表 2：基金项目 -> 处理第 4、5 章
        elif "项目" in file_name or "课题" in file_name:
            result_data["chapter_4"] = get_chapter_4_data(df, target_years)
            result_data["chapter_5_partial"] = "项目部分数据已加载，待论文数据合并"

        # 匹配 表 3：专著 -> 处理第 6 章
        elif "专著" in file_name:
            result_data["chapter_6"] = get_chapter_6_data(df, target_years)

        # 匹配 表 4：科研获奖 -> 处理第 7 章
        elif "获奖" in file_name:
            result_data["chapter_7"] = get_chapter_7_data(df, target_years)

        else:
            return {"status": "warning", "message": f"文件名 [{file_name}] 未匹配到已知业务表"}

        return {
            "status": "success",
            "detected_file": file_name,
            "data": result_data
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
