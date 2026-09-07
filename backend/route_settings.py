"""route_settings.py —— App 内改后端配置（API key / provider / 模型 / 角色默认值）

配置优先级：DB settings 表 > 环境变量 > 代码默认值
改完立刻生效，不用重启服务、不用动 Zeabur 环境变量。

端点：
    GET  /settings   返回所有可改项当前值（密钥打码）
    PUT  /settings   传 {key: value, ...} 只改传过来的
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

import config
from db import get_conn

router = APIRouter()

# 白名单：只有这些 key 允许通过 App 改
ALLOWED = {
    'LLM_PROVIDER',
    'ANTHROPIC_KEY',
    'MODEL_MAIN',
    'MODEL_JP_AUX',
    'MODEL_CN_AUX',
    'DEEPSEEK_KEY',
    'DEEPSEEK_MODEL',
    'DEEPSEEK_BASE_URL',
    'FISH_KEY',
    'FISH_VOICE_ID',
    'USE_RAG',
    'EMBED_API_KEY',
    'EMBED_BASE_URL',
    'EMBED_MODEL',
    'EMBED_DIM',
}

# 这些是密钥，GET 时打码
SECRETS = {'ANTHROPIC_KEY', 'DEEPSEEK_KEY', 'FISH_KEY', 'EMBED_API_KEY'}


def _mask(v: str) -> str:
    if not v:
        return ''
    if len(v) > 12:
        return v[:8] + '****' + v[-4:]
    return '****'


@router.get('/settings')
async def get_settings():
    out = {}
    for key in ALLOWED:
        v = config.get_setting(key)
        out[key] = _mask(v) if key in SECRETS else v
    return JSONResponse(out)


@router.put('/settings')
async def update_settings(data: dict):
    updated, rejected = [], []
    conn = get_conn()
    cur = conn.cursor()
    for key, value in (data or {}).items():
        if key not in ALLOWED:
            rejected.append(key)
            continue
        # 密钥字段：如果传回来的是打码值，说明用户没改，跳过
        sval = '' if value is None else str(value)
        if key in SECRETS and '****' in sval:
            continue
        cur.execute(
            '''INSERT INTO settings (key, value) VALUES (%s, %s)
               ON CONFLICT (key) DO UPDATE SET
                 value = EXCLUDED.value,
                 updated_at = CURRENT_TIMESTAMP''',
            (key, sval)
        )
        updated.append(key)
    conn.commit()
    cur.close()
    conn.close()

    config.clear_settings_cache()
    rag_keys = {'USE_RAG', 'EMBED_API_KEY', 'EMBED_BASE_URL', 'EMBED_MODEL', 'EMBED_DIM',
                'DEEPSEEK_KEY', 'DEEPSEEK_BASE_URL'}
    if rag_keys & set(updated):
        try:
            import memory_search
            memory_search.init_vector_support()
        except Exception as e:
            print(f'[settings] RAG 重新初始化跳过：{e}')
    print(f'[settings] 已更新 {updated}')
    return JSONResponse({
        'ok': True,
        'updated': updated,
        'rejected': rejected or None,
    })