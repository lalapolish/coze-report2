from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import io
import requests

app = FastAPI(openapi_version="3.0.2")

class FileInput(BaseModel):
    file_url: str 

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        # 1. 下载文件
        response = requests.get(input.file_url)
        response.raise_for_status()
        content = response.content
        
        # 2. 读取 Excel
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)
        df.columns = df.columns.str.strip() # 清理列名空格

        # 3. 统一转换发表年份为数字，非数字转为 NaN
        df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        
        # 定义我们需要统计的标准年份区间
        target_years = [2020, 2021, 2022, 2023, 2024]

               # --- 第 2 章：发文规模逻辑 ---
        
        # 1. 趋势数据 (对应图)
        trend_series = df[df['发表年份'].isin(target_years)].groupby('发表年份').size()
        trend_df = trend_series.reindex(target_years, fill_value=0).reset_index()
        trend_df.columns = ['发表年份', '论文数量']
        trend_data = trend_df.to_dict(orient='records')

        # 2. 学院统计 (对应表)
        unit_table = pd.pivot_table(
            df[df['发表年份'].isin(target_years)], 
            index='所属单位', 
            columns='发表年份', 
            aggfunc='size', 
            fill_value=0
        )
        
        # 补全可能缺失的年份列
        for y in target_years:
            if y not in unit_table.columns:
                unit_table[y] = 0
        
        # 计算总计
        unit_table['总计'] = unit_table.sum(axis=1)
        unit_table = unit_table.sort_values(by='总计', ascending=False).reset_index()

        # 过滤单位
        valid_suffixes = ('学院', '学部', '图书馆', '研究院') 
        unit_table = unit_table[unit_table['所属单位'].astype(str).str.endswith(valid_suffixes, na=False)]
        
        # 插入序号
        unit_table.insert(0, '序号', range(1, len(unit_table) + 1))
        
        # 先统一重命名列名（加上“年”字）
        column_mapping = {y: f"{y}年" for y in target_years}
        unit_table = unit_table.rename(columns=column_mapping)

        # 【关键步骤：显式指定列的输出顺序】
        # 定义你想要的严格顺序
        desired_order = ['序号', '所属单位'] + [f"{y}年" for y in target_years] + ['总计']
        
        # 按照这个顺序重新排列表格列
        unit_table = unit_table[desired_order]

        # 转换成字典 (Pandas 会保留列顺序)
        unit_data = unit_table.to_dict(orient='records')


        # --- 返回结果结构 ---
        return {
            "status": "success",
            "report_title": "山东师范大学人文社会科学科研成果发展态势分析报告（2020-2024）",
            "chapter_2": {
                "title": "发文规模",
                "chart_trend": trend_data,  # 这里面现在是 '发表年份' 和 '论文数量'，且年份完整
                "table_unit": unit_data     # 这里面是序号、所属单位、2020年...总计
            }
        }

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        return {"status": "error", "message": str(e), "traceback": error_msg}

@app.get("/")
def home():
    return {"message": "论文分析 API 已就绪"}
