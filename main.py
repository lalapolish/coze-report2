from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import io
import requests
from urllib.parse import unquote

app = FastAPI(openapi_version="3.0.2")

class FileInput(BaseModel):
    file_url: str 

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        # 1. 识别文件名和文件类型
        # 使用 unquote 处理 URL 中的中文编码，例如 %E4%B8%93%E8%91%97 -> 专著
        file_name = unquote(input.file_url.split('/')[-1])
        
        # 2. 下载并读取数据
        response = requests.get(input.file_url)
        response.raise_for_status()
        df = pd.read_excel(io.BytesIO(response.content), sheet_name=0)
        df.columns = df.columns.str.strip()

        # 3. 基础清洗（通用部分：年份和单位）
        if '发表年份' in df.columns:
            df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        elif '批准年份' in df.columns: # 针对基金表
            df['发表年份'] = pd.to_numeric(df['批准年份'], errors='coerce')
        elif '获奖年份' in df.columns: # 针对获奖表
            df['发表年份'] = pd.to_numeric(df['获奖年份'], errors='coerce')

        target_years = [2020, 2021, 2022, 2023, 2024]
        def clean_unit_name(name):
            name = str(name)
            return name.split('（')[0].split('(')[0].strip()
        df['所属单位'] = df['所属单位'].apply(clean_unit_name)

        # 4. 初始化返回结果
        result = {
            "status": "success",
            "detected_file": file_name,
            "data": {}
        }

        # ---------------------------------------------------------
        # 路由分发逻辑
        # ---------------------------------------------------------

        # 情况 A：处理“科研论文”表 -> 对应第 2、3 章
        if "论文" in file_name:
            trend_data, unit_data = run_standard_stats(df, target_years)
            result["data"]["chapter_2"] = {
                "title": "科研论文发文规模分析",
                "table_1_trend": trend_data,
                "table_2_unit": unit_data
            }
            # 这里可以继续写第 3 章“发文期刊”的逻辑

        # 情况 B：处理“专著”表 -> 对应第 6 章
        elif "专著" in file_name:
            trend_data, unit_data = run_standard_stats(df, target_years)
            result["data"]["chapter_6"] = {
                "title": "人文社科著作出版规模分析",
                "table_1_trend": trend_data,
                "table_2_unit": unit_data
            }

        # 情况 C：处理“基金项目”表 -> 对应第 4 章
        elif "项目" in file_name or "课题" in file_name:
            trend_data, unit_data = run_standard_stats(df, target_years)
            result["data"]["chapter_4"] = {
                "title": "纵向科研项目立项情况分析",
                "table_1_trend": trend_data,
                "table_2_unit": unit_data
            }

        # 情况 D：处理“科研获奖”表 -> 对应第 7 章
        elif "获奖" in file_name:
            trend_data, unit_data = run_standard_stats(df, target_years)
            result["data"]["chapter_7"] = {
                "title": "人文社会科学优秀成果奖获奖分析",
                "table_1_trend": trend_data,
                "table_2_unit": unit_data
            }
        
        else:
            result["status"] = "warning"
            result["message"] = f"未识别的文件类型: {file_name}，请确保文件名包含 论文/专著/项目/获奖"

        return result

    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

# ---------------------------------------------------------
# 通用统计工具函数 (用于生成年度趋势和学院排名)
# ---------------------------------------------------------
def run_standard_stats(df, target_years):
    # 1. 趋势
    trend = df[df['发表年份'].isin(target_years)].groupby('发表年份').size().reindex(target_years, fill_value=0).reset_index()
    trend.columns = ['year', 'count']
    trend_list = trend.to_dict(orient='records')

    # 2. 学院
    unit_table = pd.pivot_table(
        df[df['发表年份'].isin(target_years)], 
        index='所属单位', columns='发表年份', aggfunc='size', fill_value=0
    )
    for y in target_years:
        if y not in unit_table.columns: unit_table[y] = 0
    
    unit_table = unit_table.reset_index()
    valid_pattern = '学院|学部|图书馆|研究院|中心'
    unit_table = unit_table[unit_table['所属单位'].str.contains(valid_pattern, na=False)]
    unit_table = unit_table[unit_table['所属单位'] != '继续教育与培训学部']
    unit_table['total'] = unit_table[target_years].sum(axis=1)
    unit_table = unit_table.sort_values(by='total', ascending=False)
    unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
    
    mapping = {'所属单位': 'unit_name', 2020: 'year_2020', 2021: 'year_2021', 2022: 'year_2022', 2023: 'year_2023', 2024: 'year_2024'}
    unit_table = unit_table.rename(columns=mapping)
    order = ['id', 'unit_name', 'year_2020', 'year_2021', 'year_2022', 'year_2023', 'year_2024', 'total']
    return trend_list, unit_table[order].to_dict(orient='records')

@app.get("/")
def home():
    return {"message": "API 已更新：支持按文件名动态路由章节逻辑"}
