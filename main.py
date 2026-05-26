from fastapi import FastAPI, UploadFile, File
import pandas as pd
import io

# 创建 API 应用
app = FastAPI(title="山东师范大学科研报告解析API")

# ==========================================
# 这里是我们刚才写的核心处理逻辑
# ==========================================
def process_chapter_2(df):
    # 步骤0：基础数据过滤
    df['发表年份'] = pd.to_numeric(df['发表年份'], errors='coerce')
    df = df[(df['发表年份'] >= 2020) & (df['发表年份'] <= 2024)]
    
    # 产出 1：图1
    trend_data = df.groupby('发表年份').size().reset_index(name='论文数量')
    trend_data_dict = trend_data.to_dict(orient='records') 
    
    # 产出 2：表1
    unit_table = pd.pivot_table(df, index='所属单位', columns='发表年份', aggfunc='size', fill_value=0)
    unit_table['总计'] = unit_table.sum(axis=1)
    unit_table = unit_table.sort_values(by='总计', ascending=False).reset_index()
    
    def keep_unit(unit_name):
        valid_suffixes = ('学院', '学部', '图书馆', '研究院')
        return str(unit_name).endswith(valid_suffixes)
        
    unit_table = unit_table[unit_table['所属单位'].apply(keep_unit)]
    unit_table = unit_table.head(23)
    unit_table.insert(0, '序号', range(1, len(unit_table) + 1))
    
    unit_table.columns = [str(c) for c in unit_table.columns]
    unit_table_dict = unit_table.to_dict(orient='records')
    
    return trend_data_dict, unit_table_dict

# ==========================================
# 开放给 Coze 调用的 API 接口
# ==========================================
@app.post("/parse_report")
async def parse_report(file: UploadFile = File(...)):
    """
    接收上传的 Excel 文件，并返回解析后的 JSON 数据
    """
    # 1. 读取工作流传过来的 Excel 文件流
    contents = await file.read()
    
    # 2. 用 Pandas 解析 Excel 
    # (这里假设传来的Excel可以直接读，如果你的样例数据叫'论文'sheet，可以加上 sheet_name='论文')
    df_paper = pd.read_excel(io.BytesIO(contents))
    
    # 3. 调用第二章处理逻辑
    ch2_trend, ch2_unit = process_chapter_2(df_paper)
    
    # 4. 组装返回给 Coze 的终极 JSON
    final_response = {
        "report_info": {
            "title": "山东师范大学人文社会科学科研成果发展态势分析报告（2020-2024）"
        },
        "chapters": {
            "chapter_2": {
                "chapter_title": "2 发文规模",
                "data": {
                    "chart_1": {
                        "title": "图1 2020-2024年我校人文社科发文量变化",
                        "content": ch2_trend
                    },
                    "table_1": {
                        "title": "表1 2020-2024年我校各学院人文社科发文量统计",
                        "content": ch2_unit
                    }
                }
            }
        }
    }
    
    return final_response

# 添加一个简单的健康检查接口，方便在浏览器里测试服务是否正常运行
@app.get("/")
def read_root():
    return {"message": "API 服务已成功运行！请使用 POST /parse_report 接口上传文件。"}

