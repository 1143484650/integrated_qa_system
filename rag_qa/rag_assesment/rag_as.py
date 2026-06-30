# -*-coding:utf-8-*-
# 导入pandas库，用于数据处理和保存CSV文件
import pandas as pd

import sys, os,json
current_dir = os.path.dirname(os.path.abspath(__file__))
rag_qa_path = os.path.dirname(current_dir)
sys.path.insert(0, rag_qa_path)
project_root = os.path.dirname(rag_qa_path)
sys.path.insert(0, project_root)


# 导入ragas库的evaluate函数，用于执行RAG评估
from ragas import evaluate
# 导入ragas的评估指标，包括忠实度、答案相关性、上下文相关性和上下文召回率
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall
)
# 导入datasets库的Dataset类，用于构建RAGAS所需的数据格式
from datasets import Dataset
# 导入langchain_openai的嵌入模型和聊天模型，用于评估时的语义计算和推理
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
# 导入langchain_community的Ollama聊天模型和嵌入模型，用于本地模型调用
from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings,DashScopeEmbeddings

from base import logger, Config



# 1. 加载生成的数据集,转json

# 2. 转换为RAGAS格式 {question,contexts,answer,ground_truth}


# 3. 将字典转换为RAGAS所需的Dataset对象


# 3. 配置RAGAS评估环境
# 初始化ChatOpenAI模型
# llm = ChatOpenAI(model=Config().LLM_MODEL, api_key = Config().DASHSCOPE_API_KEY,base_url = Config().DASHSCOPE_BASE_URL)
# embeddings = DashScopeEmbeddings(model="text-embedding-v1",dashscope_api_key=Config().DASHSCOPE_API_KEY)

# 初始化ChatOllama模型
llm = ChatOllama(model="qwen2.5:7b", base_url='http://localhost:11434')
embeddings = OllamaEmbeddings(model="qwen2.5:7b",base_url='http://localhost:11434' )

# 4. 执行评估
# 调用evaluate函数，传入数据集、评估指标、LLM模型和嵌入模型
# evaluate(dataset,metrics,llm,embeddings)


# 5. 打印评估结果







