from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd
import io
import requests

# 保持你之前的初始化方式
app = FastAPI(openapi_version="3.0.2")

class FileInput(BaseModel):
    file_url: str  # 扣子传过来的 Excel 文件链接

@app.post("/analyze_report")
async def analyze_report(input: FileInput):
    try:
        # 1. 下载文件
        response = requests.get(input.file_url)
        response.raise_for_status()
        content = response.content
        
        # 2. 读取 Excel (注意这里改成了 read_excel)
        # 默认读取第一个 Sheet。如果你的表在特定 Sheet，可以加 sheet_name='论文'
        df = pd.read_excel(io.BytesIO(content))

        # --- 统一清洗数据 ---
        df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
        # 过滤 2020-2024
        df_filtered = df[(df['发表年份'] >= 2020) & (df['发表年份'] <= 2024)].copy()

        # --- 第2章：发文规模逻辑 ---
        
        # 1. 趋势数据 (图1)
        trend_df = df_filtered.groupby('发表年份').size().reset_index(name='count')
        trend_data = trend_df.to_dict(orient='records')

        # 2. 学院统计 (表1)
        unit_table = pd.pivot_table(
            df_filtered, 
            index='所属单位', 
            columns='发表年份', 
            aggfunc='size', 
            fill_value=0
        )
        unit_table['total'] = unit_table.sum(axis=1)
        unit_table = unit_table.sort_values(by='total', ascending=False).reset_index()

        # 学院过滤逻辑
        valid_suffixes = ('学院', '学部', '图书馆', '研究院')
        unit_table = unit_table[unit_table['所属单位'].str.endswith(valid_suffixes, na=False)]
        unit_table = unit_table.head(23) # 取前23个
        unit_table.insert(0, 'id', range(1, len(unit_table) + 1))
        
        # 转换列名为字符串防止 JSON 报错
        unit_table.columns = [str(c) for c in unit_table.columns]
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
                    "total_count": len(df_filtered),
                    "top_unit": unit_table.iloc[0]['所属单位'] if not unit_table.empty else "无"
                }
            }
            # 以后加第3章、第4章就在这里扩展
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

# 健康检查
@app.get("/")
def home():
    return {"message": "论文分析 API 已就绪"}
