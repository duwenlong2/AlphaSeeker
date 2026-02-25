#!/usr/bin/env python3
"""
多提供商模型测试脚本（仅系统环境变量）
支持 Azure OpenAI / DeepSeek 切换
"""

import os
import sys
import json
from typing import Any

from openai import AzureOpenAI, OpenAI


SUPPORTED_PROVIDERS = {"azure", "deepseek"}


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"缺少环境变量: {name}")
    return value


def get_provider() -> str:
    """读取提供商（默认 azure）。"""
    provider = os.getenv("LLM_PROVIDER", "azure").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER 仅支持 {sorted(SUPPORTED_PROVIDERS)}，当前为: {provider}"
        )
    return provider


def create_client_and_model() -> tuple[Any, str, str]:
    """创建客户端并返回 (client, model, provider)。"""
    provider = get_provider()

    if provider == "azure":
        endpoint = _require_env("AZURE_OPENAI_ENDPOINT")
        api_key = _require_env("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
        model = _require_env("AZURE_OPENAI_DEPLOYMENT")

        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        return client, model, provider

    # deepseek
    api_key = _require_env("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model, provider


def chat_with_model(client: Any, message: str, model: str, max_tokens: int = 1000):
    """
    与模型对话的基础函数

    Args:
        client: OpenAI客户端实例
        message: 用户消息
        model: 模型名称（Azure 填 deployment 名，DeepSeek 填 model 名）
        max_tokens: 最大token数

    Returns:
        dict: 包含响应内容和使用情况的字典
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": message}],
            max_completion_tokens=max_tokens
        )

        content = response.choices[0].message.content
        usage = response.usage

        return {
            "success": True,
            "content": content,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def test_basic_chat():
    """基础聊天测试"""
    print("=== 基础测试（多提供商）===")

    # 创建客户端
    try:
        client, model, provider = create_client_and_model()
        print(f"✓ 客户端创建成功，provider={provider}, model={model}")
    except Exception as e:
        print(f"✗ 客户端创建失败: {e}")
        return

    # 测试消息
    test_message = "你好，请介绍一下你自己。"

    print(f"发送消息: {test_message}")

    # 调用模型
    result = chat_with_model(client, test_message, model=model)

    if result["success"]:
        print("✓ 模型调用成功")
        print(f"响应内容: {result['content']}")
        print(f"Token使用: {result['usage']}")
    else:
        print(f"✗ 模型调用失败: {result['error']}")

def test_custom_prompt():
    """自定义提示词测试"""
    print("\n=== 自定义提示词测试 ===")

    client, model, provider = create_client_and_model()
    print(f"provider={provider}, model={model}")

    # 自定义系统提示词
    system_prompt = "你是一个专业的Python编程助手，请用简洁的语言回答问题。"

    # 用户问题
    user_message = f"{system_prompt}\n\n用户: 如何在Python中读取环境变量？"

    result = chat_with_model(client, user_message, model=model)

    if result["success"]:
        print("✓ 自定义提示词测试成功")
        print(f"响应: {result['content']}")
    else:
        print(f"✗ 测试失败: {result['error']}")

def test_json_output():
    """JSON输出格式测试"""
    print("\n=== JSON输出格式测试 ===")

    client, model, provider = create_client_and_model()
    print(f"provider={provider}, model={model}")

    prompt = """请分析以下Python代码，返回JSON格式的结果：

def hello_world():
    print("Hello, World!")

请返回以下JSON格式：
{
    "function_name": "函数名",
    "description": "函数描述",
    "complexity": "复杂度评估"
}"""

    result = chat_with_model(client, prompt, model=model, max_tokens=500)

    if result["success"]:
        print("✓ JSON测试成功")
        print(f"原始响应: {result['content']}")

        # 尝试解析JSON
        try:
            content = result['content'].strip()
            # 提取JSON部分
            if content.startswith('{') and content.endswith('}'):
                json_data = json.loads(content)
                print(f"解析后的JSON: {json.dumps(json_data, ensure_ascii=False, indent=2)}")
            else:
                print("响应不是纯JSON格式")
        except json.JSONDecodeError as e:
            print(f"JSON解析失败: {e}")
    else:
        print(f"✗ 测试失败: {result['error']}")

def main():
    """主函数"""
    print("模型测试脚本（Azure / DeepSeek）")
    print("=" * 50)

    # 检查环境变量
    print("环境变量检查:")
    provider = os.getenv("LLM_PROVIDER", "azure")
    print(f"LLM_PROVIDER: {provider}")
    print(f"AZURE_OPENAI_ENDPOINT: {os.getenv('AZURE_OPENAI_ENDPOINT', '未设置')}")
    print(f"AZURE_OPENAI_API_KEY: {'已设置' if os.getenv('AZURE_OPENAI_API_KEY') else '未设置'}")
    print(f"AZURE_OPENAI_DEPLOYMENT: {os.getenv('AZURE_OPENAI_DEPLOYMENT', '未设置')}")
    print(f"DEEPSEEK_BASE_URL: {os.getenv('DEEPSEEK_BASE_URL', '未设置(默认 https://api.deepseek.com/v1)')}")
    print(f"DEEPSEEK_API_KEY: {'已设置' if os.getenv('DEEPSEEK_API_KEY') else '未设置'}")
    print(f"DEEPSEEK_MODEL: {os.getenv('DEEPSEEK_MODEL', '未设置(默认 deepseek-chat)')}")
    print()

    # 运行测试
    try:
        test_basic_chat()
        test_custom_prompt()
        test_json_output()

        print("\n=== 测试完成 ===")
        print("✓ 所有测试运行完毕，请检查上述输出")

    except KeyboardInterrupt:
        print("\n用户中断测试")
    except Exception as e:
        print(f"\n测试过程中发生错误: {e}")

if __name__ == "__main__":
    main()