"""Content scope guardrail — enforces topic boundaries for PnLClaw AI.

Implements three layers of defense:
1. Input guard: prompt injection detection + off-topic blocking
2. Scope enforcement: classify messages into allowed/blocked topics
3. Output guard: redact internal system information from AI responses

References:
- OWASP LLM Top 10 (2025) - LLM01: Prompt Injection
- AWS LLM Prompt Engineering Best Practices
- NVIDIA NeMo Guardrails TopicControl pattern
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class GuardAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"


class MessageTopic(str, Enum):
    GREETING = "greeting"
    MARKET_ANALYSIS = "market_analysis"
    STRATEGY = "strategy"
    TRADING = "trading"
    KNOWLEDGE_TRADING = "knowledge_trading"
    SYSTEM_PROBE = "system_probe"
    PROMPT_INJECTION = "prompt_injection"
    OFF_TOPIC = "off_topic"
    SECRET_EXTRACTION = "secret_extraction"


@dataclass(frozen=True)
class GuardResult:
    action: GuardAction
    topic: MessageTopic
    reason: str
    sanitized_message: str | None = None
    canned_response: str | None = None


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

_PROMPT_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_instructions", re.compile(
        r"(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+)?(?:previous|prior|above|your|system)\s+"
        r"(?:instructions?|prompts?|rules?|guidelines?|constraints?|restrictions?)",
        re.IGNORECASE,
    )),
    ("role_hijack", re.compile(
        r"(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you(?:'re|\s+are))|roleplay\s+as|switch\s+to)\s+",
        re.IGNORECASE,
    )),
    ("new_instructions", re.compile(r"new\s+instructions?\s*:", re.IGNORECASE)),
    ("system_override", re.compile(
        r"(?:system\s*:?\s*(?:prompt|override|command)|</?system>|\[system\s*(?:message)?\])",
        re.IGNORECASE,
    )),
    ("jailbreak_dan", re.compile(
        r"(?:DAN|do\s+anything\s+now|developer\s+mode|jailbreak|uncensor)",
        re.IGNORECASE,
    )),
    ("prompt_leak", re.compile(
        r"(?:show|reveal|print|output|repeat|display|give\s+me)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions|rules|guidelines)",
        re.IGNORECASE,
    )),
    ("chat_template_marker", re.compile(
        r"<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>",
        re.IGNORECASE,
    )),
    ("base64_injection", re.compile(
        r"(?:decode|base64|eval|exec)\s*\(",
        re.IGNORECASE,
    )),
]

_SECRET_EXTRACTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ask_api_key", re.compile(
        r"(?:告诉|给|show|tell|reveal|what(?:'s|\s+is))\s*(?:我|me)?\s*(?:你的|your)?\s*"
        r"(?:api\s*key|secret|密钥|密码|password|token|credential|配置|config)",
        re.IGNORECASE,
    )),
    ("ask_env_var", re.compile(
        r"(?:环境变量|env(?:ironment)?\s*var|\.env|config\.(?:yaml|json|toml)|OPENAI_|API_BASE|BASE_URL|LLM_|"
        r"(?:忘了|忘记).{0,15}(?:API|api|地址|url|配置|config|密钥|key))",
        re.IGNORECASE,
    )),
    ("ask_system_info", re.compile(
        r"(?:你的|your)\s*(?:技术栈|tech\s*stack|架构|architecture|源码|source\s*code|部署|deploy|服务器|server|模型|model\s+(?:name|version|weights))",
        re.IGNORECASE,
    )),
    ("ask_internal", re.compile(
        r"(?:内部|internal)\s*(?:实现|implementation|设计|design|代码|code|逻辑|logic)",
        re.IGNORECASE,
    )),
]

_ALLOWED_TOPIC_PATTERNS: list[tuple[MessageTopic, re.Pattern[str]]] = [
    (MessageTopic.GREETING, re.compile(
        r"^(?:你好|hi|hello|hey|嗨|哈喽|在吗|good\s+(?:morning|afternoon|evening)|谢谢|thanks|thank\s+you|再见|bye|怎么用|help|帮助"
        r"|卡住了吗|卡住了|卡了|还在吗|还在运行吗|怎么了|怎么回事|好了吗|完了吗|结束了吗|出错了吗"
        r"|继续|继续吧|接着|接着说|下一步|然后呢|接下来呢"
        r"|好的|好|行|嗯|ok|okay|可以|没问题|收到|明白|了解|知道了"
        r"|是的?|对的?|不是|不对|不要|取消|算了|停|停止|重来|重新来"
        r"|为什么|什么意思|没看懂|看不懂|能.{0,20}(?:详细|解释|说明).*"
        r"|(?:1|2|3|4|5|6|7|8|9|A|B|C|D)\s*$"
        r")\s*[!！。.？?~～…]*$",
        re.IGNORECASE,
    )),
    (MessageTopic.MARKET_ANALYSIS, re.compile(
        r"(?:分析|行情|趋势|价格|涨|跌|走势|K线|k线|均线|macd|rsi|ema|sma|支撑|阻力|"
        r"orderbook|订单簿|盘口|波动|突破|震荡|反转|动量|成交量|volume|"
        r"analyze|analysis|market|price|trend|support|resistance|candle|chart|"
        r"btc|eth|sol|bnb|doge|xrp|usdt|ada|avax|dot|matic|link|"
        r"bitcoin|比特币|以太坊|ethereum|solana|binance|okx|bybit|coinbase|"
        r"现货|合约|futures|spot|swap|永续|perpetual|大盘|币圈|加密货币|crypto)",
        re.IGNORECASE,
    )),
    (MessageTopic.STRATEGY, re.compile(
        r"(?:策略|strategy|回测|backtest|参数|parameter|优化|optimize|"
        r"入场|entry|出场|exit|止损|stop.?loss|止盈|take.?profit|"
        r"仓位|position\s*siz|风控|risk|sharpe|drawdown|回撤|"
        r"alpha|因子|factor|信号|signal|指标|indicator|"
        r"量化|quant|systematic|algo|算法)",
        re.IGNORECASE,
    )),
    (MessageTopic.TRADING, re.compile(
        r"(?:交易|trade|trading|开仓|平仓|持仓|下单|order|"
        r"买|卖|buy|sell|long|short|做多|做空|"
        r"paper|模拟|simulation|账户|account|余额|balance|"
        r"盈亏|pnl|profit|loss|收益)",
        re.IGNORECASE,
    )),
    (MessageTopic.KNOWLEDGE_TRADING, re.compile(
        r"(?:什么是.{0,5}(?:K线|均线|macd|rsi|布林|趋势|支撑|阻力|期货|现货|合约|杠杆|保证金|"
        r"止损|止盈|仓位|风控|回撤|夏普|对冲|套利|做市|流动性|滑点|手续费|"
        r"交易所|钱包|区块链|defi|nft|挖矿|质押|gas|"
        r"technical\s*analysis|fundamental|sentiment|on.?chain)|"
        r"怎么.{0,5}(?:交易|做多|做空|开仓|平仓|止损|回测|"
        r"分析|看盘|选币|配置|设置)|"
        r"(?:explain|what\s+is|how\s+to).{0,30}(?:trading|crypto|bitcoin|indicator|strategy|backtest))",
        re.IGNORECASE,
    )),
]

# Output redaction patterns
_OUTPUT_REDACT_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("tech_stack_leak", re.compile(
        r"(?:我的技术栈|我的架构|我基于|我使用了|我的底层|my\s+(?:tech\s*stack|architecture|underlying)|"
        r"I\s+(?:am\s+built|run\s+on|use)\s+(?:on\s+)?(?:GPT|Claude|Llama|Gemini|Mistral|Qwen|DeepSeek))",
        re.IGNORECASE,
    ), "[系统信息不可公开]"),
    ("env_var_leak", re.compile(
        r"(?:OPENAI_(?:API_KEY|BASE_URL|API_BASE)|API_(?:KEY|SECRET|BASE)|"
        r"LLM_(?:API|URL|KEY)|(?:\.env|config\.yaml|docker-compose)\s*(?:文件|file)?(?:里|中|in)?)",
        re.IGNORECASE,
    ), "[配置信息已隐藏]"),
    ("model_name_leak", re.compile(
        r"\b(?:gpt-4|gpt-3\.5|claude-[23]|llama-[23]|gemini-(?:pro|ultra)|mistral|qwen|deepseek)\b",
        re.IGNORECASE,
    ), "[模型名称已隐藏]"),
    ("internal_path_leak", re.compile(
        r"(?:packages/|services/|apps/|src/|node_modules/|__pycache__|\.git/|"
        r"pnlclaw_(?:agent|security|exchange|market|paper|strategy|llm|storage))",
        re.IGNORECASE,
    ), "[内部路径已隐藏]"),
]

# Canned responses for blocked topics
_BLOCK_RESPONSES: dict[MessageTopic, str] = {
    MessageTopic.OFF_TOPIC: (
        "抱歉，我是 PnLClaw 加密交易助手，只能帮你处理以下事项：\n"
        "• 行情分析（价格、趋势、技术指标）\n"
        "• 策略研发（生成、回测、优化）\n"
        "• 模拟交易（下单、持仓、盈亏）\n"
        "• 交易知识（指标、风控、概念）\n\n"
        "请问有什么交易相关的问题我可以帮你？"
    ),
    MessageTopic.PROMPT_INJECTION: (
        "检测到异常输入。我是 PnLClaw 加密交易助手，"
        "无法执行与交易分析无关的指令。"
    ),
    MessageTopic.SECRET_EXTRACTION: (
        "出于安全考虑，我无法提供任何系统配置、API 密钥、"
        "环境变量或内部架构信息。\n\n"
        "如需查看你的配置，请直接在本地项目文件中查找。"
    ),
    MessageTopic.SYSTEM_PROBE: (
        "我是 PnLClaw 加密交易助手。出于安全策略，"
        "我不会讨论自身的技术实现、底层模型或系统架构。\n\n"
        "有什么交易相关的问题我可以帮你？"
    ),
}


# ---------------------------------------------------------------------------
# Guard engine
# ---------------------------------------------------------------------------


class ContentScopeGuard:
    """Three-layer content security guardrail.

    Layer 1 (Input): Detect prompt injection and secret extraction attempts.
    Layer 2 (Scope): Classify topic and block off-topic messages.
    Layer 3 (Output): Redact internal information from AI responses.
    """

    def check_input(self, message: str) -> GuardResult:
        """Evaluate user input and return a guard decision."""
        normalized = message.strip()
        if not normalized:
            return GuardResult(
                action=GuardAction.BLOCK,
                topic=MessageTopic.OFF_TOPIC,
                reason="empty_message",
                canned_response="请输入你的问题。",
            )

        # Layer 1: Prompt injection detection
        for name, pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(normalized):
                logger.warning(
                    "Prompt injection detected: pattern=%s, message=%s",
                    name, normalized[:100],
                )
                return GuardResult(
                    action=GuardAction.BLOCK,
                    topic=MessageTopic.PROMPT_INJECTION,
                    reason=f"injection:{name}",
                    canned_response=_BLOCK_RESPONSES[MessageTopic.PROMPT_INJECTION],
                )

        # Layer 1b: Secret extraction detection
        for name, pattern in _SECRET_EXTRACTION_PATTERNS:
            if pattern.search(normalized):
                logger.warning(
                    "Secret extraction attempt: pattern=%s, message=%s",
                    name, normalized[:100],
                )
                return GuardResult(
                    action=GuardAction.BLOCK,
                    topic=MessageTopic.SECRET_EXTRACTION,
                    reason=f"secret_extraction:{name}",
                    canned_response=_BLOCK_RESPONSES[MessageTopic.SECRET_EXTRACTION],
                )

        # Layer 2: Topic classification
        topic = self._classify_topic(normalized)

        if topic == MessageTopic.SYSTEM_PROBE:
            return GuardResult(
                action=GuardAction.BLOCK,
                topic=topic,
                reason="system_probe",
                canned_response=_BLOCK_RESPONSES[MessageTopic.SYSTEM_PROBE],
            )

        if topic == MessageTopic.OFF_TOPIC:
            logger.info(
                "Off-topic message allowed through to LLM: %s",
                normalized[:80],
            )
            return GuardResult(
                action=GuardAction.WARN,
                topic=topic,
                reason="off_topic_passthrough",
            )

        return GuardResult(
            action=GuardAction.ALLOW,
            topic=topic,
            reason="on_topic",
            sanitized_message=normalized,
        )

    def filter_output(self, response: str) -> str:
        """Redact internal information from AI response text."""
        result = response
        for name, pattern, replacement in _OUTPUT_REDACT_PATTERNS:
            if pattern.search(result):
                logger.warning("Output redaction triggered: %s", name)
                result = pattern.sub(replacement, result)
        return result

    def _classify_topic(self, message: str) -> MessageTopic:
        """Classify the user message into a topic category."""
        for topic, pattern in _ALLOWED_TOPIC_PATTERNS:
            if pattern.search(message):
                return topic

        if self._is_system_probe(message):
            return MessageTopic.SYSTEM_PROBE

        return MessageTopic.OFF_TOPIC

    @staticmethod
    def _is_system_probe(message: str) -> bool:
        """Detect attempts to probe system internals."""
        probes = [
            re.compile(r"(?:你是|你用|你的|你基于)\s*(?:什么|哪个|哪种)\s*(?:模型|AI|技术|框架|语言)", re.IGNORECASE),
            re.compile(r"(?:what|which)\s+(?:model|AI|LLM|framework|language)", re.IGNORECASE),
            re.compile(r"(?:你|你的)\s*(?:代码|源码|仓库|repo|github)", re.IGNORECASE),
            re.compile(r"(?:技术栈|tech\s*stack|底层|underlying|behind\s+the\s+scenes)", re.IGNORECASE),
            re.compile(r"(?:怎么部署|how.*deploy|运行.*(?:在|on).*(?:哪|where))", re.IGNORECASE),
        ]
        for p in probes:
            if p.search(message):
                return True
        return False
