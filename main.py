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
        
        # 2. 读取 Excel (指定读取第一个 sheet，通常索引是 0)
        # 注意：这里需要确保你的 requirements.txt 中安装了 openpyxl
        df = pd.read_excel(io.BytesIO(content), sheet_name=0)

        # 清理列名空格，防止因为列名有多余空格导致找不到列
        df.columns = df.columns.str.strip()

        # 确保发表年份是整数类型（去掉可能的浮点数或字符串影响）
        df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce').fillna(0).astype(int)

        # --- 第2章：发文规模逻辑 ---
        
        # 1. 趋势数据 (对应图：发文量变化)
        # 过滤出2020-2024年的数据仅用于统计，哪怕你说已经处理过，这里加个条件更保险
        trend_df = df[df['发表年份'].isin([2020, 2021, 2022, 2023, 2024])].groupby('发表年份').size().reset_index(name='count')
        # 转换成字典列表
        trend_data = trend_df.to_dict(orient='records')

        # 2. 学院统计 (对应表：各学院发文量统计)
        unit_table = pd.pivot_table(
            df, 
            index='所属单位', 
            columns='发表年份', 
            aggfunc='size', 
            fill_value=0
        )
        
        # 计算总计
        unit_table['总计'] = unit_table.sum(axis=1)
        
        # 按总计降序排列
        unit_table = unit_table.sort_values(by='总计', ascending=False).reset_index()

        # 学院过滤逻辑：只保留学院、学部、图书馆、研究院
        valid_suffixes = ('学院', '学部', '图书馆', '研究院')
        unit_table = unit_table[unit_table['所属单位'].astype(str).str.endswith(valid_suffixes, na=False)]
        
        # 插入序号列 (id)
        unit_table.insert(0, '序号', range(1, len(unit_table) + 1))
        
        # 格式化列名，把 2020 变成 "2020年"
        new_columns = []
        for col in unit_table.columns:
            if isinstance(col, int) or (isinstance(col, str) and col.isdigit()):
                new_columns.append(f"{col}年")
            else:
                new_columns.append(str(col))
        unit_table.columns = new_columns

        # 转换成字典
        unit_data = unit_table.to_dict(orient='records')

        # --- 返回结果结构 ---
        return {
            "status": "success",
            "report_title": "山东师范大学人文社会科学科研成果发展态势分析报告（2020-2024）",
            "chapter_2": {
                "title": "发文规模",
                "chart_trend": trend_data,
                "table_unit": unit_data,
                "summary": {
                    "total_count": int(df.shape[0]),
                    "top_unit": unit_table.iloc[0]['所属单位'] if not unit_table.empty else "无"
                }
            }
        }

    except Exception as e:
        # 打印详细错误方便排查
        import traceback
        error_msg = traceback.format_exc()
        return {"status": "error", "message": str(e), "traceback": error_msg}

@app.get("/")
def home():
    return {"message": "论文分析 API 已就绪"}
