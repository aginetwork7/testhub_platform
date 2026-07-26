from pathlib import Path
from decouple import config
import os
import logging

from .config_loader import config_loader
from .log_config import log_config

# 当前文件所在路径
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = log_config.log_dir

# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)


SECRET_KEY = config('SECRET_KEY', default=config_loader.get('server.secret_key',
                                                            'django-insecure-6wf7pmw0mzh%(^/4%qa/3o5nfg7xmqyi8mewwbyyqmna7ertm9'))

DEBUG = config('DEBUG', default=config_loader.get('server.debug', True), cast=bool)

# 后端服务端口（开发环境）
BACKEND_PORT = config('BACKEND_PORT', default=config_loader.get('server.backend_port', 8001), cast=int)

# 前端服务URL（用于生成报告链接等）
FRONTEND_URL = config('FRONTEND_URL', default=config_loader.get('server.frontend_url', 'http://localhost:3000'))

# 根据DEBUG模式设置ALLOWED_HOSTS，生产环境不应使用通配符
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1',
                           cast=lambda v: [s.strip() for s in v.split(',')])

DJANGO_APPS = [
    'simpleui',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'channels',
    'django_q',
]

LOCAL_APPS = [
    'apps.users',
    'apps.projects',
    'apps.testcases',
    'apps.testsuites',
    'apps.executions',
    'apps.reports',
    'apps.reviews',
    'apps.versions',
    'apps.assistant',
    'apps.requirement_analysis',
    'apps.knowledge_base.apps.KnowledgeBaseConfig',
    'apps.api_testing',
    'apps.api_automation.apps.ApiAutomationConfig',
    'apps.ui_automation.apps.UiAutomationConfig',
    'apps.app_automation.apps.AppAutomationConfig',
    'apps.ai_testing',
    'apps.scheduler',
    'apps.core',
    'apps.data_factory',
    'apps.unified_projects.apps.UnifiedProjectsConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'backend.middleware.DisableCSRFMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'backend.middleware.async_middleware.AsyncRequestTimingMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

db_config = config_loader.get_database_config()
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', default=db_config.get('name', 'testhub')),
        'USER': config('DB_USER', default=db_config.get('user', 'test_platform')),
        'PASSWORD': config('DB_PASSWORD', default=db_config.get('password', '')),
        'HOST': config('DB_HOST', default=db_config.get('host', '127.0.0.1')),
        'PORT': config('DB_PORT', default=db_config.get('port', 3306)),
        'CONN_MAX_AGE': 60,
        'ATOMIC_REQUESTS': True,
        'OPTIONS': {
            'charset': db_config.get('charset', 'utf8mb4'),
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES', time_zone='+08:00'",
            'connect_timeout': 10,
            'read_timeout': 30,
            'write_timeout': 30,
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = config('LANGUAGE_CODE', default='zh-hans')
TIME_ZONE = config('TIME_ZONE', default='Asia/Shanghai')
USE_I18N = True
USE_TZ = True

# 国际化配置 - 支持简体中文和英文
LANGUAGES = [
    ('zh-hans', '简体中文'),
    ('en', 'English'),
]

# 翻译文件路径
LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# Whitenoise 配置 - 用于在生产环境提供静态文件
WHITENOISE_USE_FINDERS = True
WHITENOISE_IGNORE_REGEX = r'^(?!/static/).*\.html$'

# 静态文件目录配置
STATIC_FILES_ROOT = os.path.join(BASE_DIR, 'static_files')
STATICFILES_DIRS = [STATIC_FILES_ROOT]

# 自动创建静态文件目录（如果不存在）
os.makedirs(STATIC_FILES_ROOT, exist_ok=True)

# 数据工厂的静态文件目录
STATIC_FILES_URL = '/static_files/'

MEDIA_URL = '/media/'

# Allure 配置
allure_config = config_loader.get_allure_config()
ALLURE_BIN_PATH = allure_config.get('bin_path', 'expand/allure/bin')
ALLURE_STATIC_DIR = allure_config.get('static_dir', 'static')
ALLURE_REPORTS_DIR = allure_config.get('reports_dir', 'allure-reports')
ALLURE_RESULTS_DIR = allure_config.get('results_dir', 'allure-results')
ALLURE_AI_RECORDING = allure_config.get('ai_recording', 'ai_recording')
ALLURE_API_TESTING = allure_config.get('api_testing', 'api_testing')
ALLURE_APP_AUTOMATION = allure_config.get('app_automation', 'app_automation')

# 路径配置
paths_config = config_loader.get_paths_config()
# Media 文件根目录 - 使用配置文件中的路径
MEDIA_ROOT = os.path.join(BASE_DIR.parent, paths_config.get('media_root', 'media'))
PATHS_APP_AUTOMATION_TEMPLATE = paths_config.get('app_automation_template', 'apps/app_automation/Template')
PATHS_UI_COMPONENT_PACK = paths_config.get('ui_component_pack', 'apps/core/management/commands/ui-component-pack.yaml')
PATHS_DATA_FACTORY_STATIC_IMG = paths_config.get('data_factory_static_img', 'static_files/img')
PATHS_APP_AUTOMATION_SCREENSHOTS = paths_config.get('app_automation_screenshots', 'app-automation/screenshots')
PATHS_UI_AUTOMATION_SCREENSHOTS = paths_config.get('ui_automation_screenshots', 'ui_automation/screenshots')
PATHS_CHROMA_DB = paths_config.get('chroma_db', '../expand/chroma_db')


# 超时配置
timeouts_config = config_loader.get_timeouts_config()
TIMEOUTS_API_REQUEST = timeouts_config.get('api_request', 30)
TIMEOUTS_ALLURE_REPORT = timeouts_config.get('allure_report', 30)
TIMEOUTS_PROCESS_WAIT = timeouts_config.get('process_wait', 5)
TIMEOUTS_TEST_EXECUTION = timeouts_config.get('test_execution', 60)
TIMEOUTS_AI_REQUEST = timeouts_config.get('ai_request', 60)
TIMEOUTS_AI_FAST_REQUEST = timeouts_config.get('ai_fast_request', 3.0)
TIMEOUTS_PAGE_LOAD_NETWORKIDLE = timeouts_config.get('page_load_networkidle', 10000)
TIMEOUTS_PAGE_LOAD_DOMCONTENTLOADED = timeouts_config.get('page_load_domcontentloaded', 5000)
TIMEOUTS_ELEMENT_CLICK = timeouts_config.get('element_click', 2000)
TIMEOUTS_ELEMENT_SCROLL = timeouts_config.get('element_scroll', 5000)
TIMEOUTS_SCREENSHOT = timeouts_config.get('screenshot', 5000)

# 缓存配置
cache_config = config_loader.get_cache_config()
CACHE_OCR_MAX_SIZE = cache_config.get('ocr_max_size', 50)
OCR_USE_GPU = config('OCR_USE_GPU', default=cache_config.get('ocr_use_gpu', False), cast=bool)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# DRF Settings
throttling_config = config_loader.get_throttling_config()
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # JWT认证（优先）
        'rest_framework.authentication.TokenAuthentication',  # 保留Token认证（兼容）
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': throttling_config.get('anon_rate', '100/hour'),
        'user': throttling_config.get('user_rate', '1000/hour')
    },
}

# JWT Settings
from datetime import timedelta

jwt_config = config_loader.get_jwt_config()
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=jwt_config.get('access_token_lifetime', 15)),  # access_token 15分钟（优化安全性）
    'REFRESH_TOKEN_LIFETIME': timedelta(days=jwt_config.get('refresh_token_lifetime', 7)),  # refresh_token 7天
    'ROTATE_REFRESH_TOKENS': jwt_config.get('rotate_refresh_tokens', True),  # 刷新时轮换refresh_token
    'BLACKLIST_AFTER_ROTATION': jwt_config.get('blacklist_after_rotation', True),  # 旧的refresh_token加入黑名单
    'UPDATE_LAST_LOGIN': True,  # 更新最后登录时间

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# CSRF Settings - 根据DEBUG模式设置
if DEBUG:
    CSRF_COOKIE_SECURE = False
    CSRF_USE_SESSIONS = False
    CSRF_COOKIE_HTTPONLY = False
    CSRF_COOKIE_SAMESITE = 'Lax'
else:
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = 'Strict'


# CORS Settings (Django 6 内置) 优先使用 config.yaml 中的跨域配置
cors_config = config_loader.get_cors_config()

cors_origins_config = cors_config.get('allowed_origins', [])
# 如果 config.yaml 中没有配置，再从环境变量中获取
if not cors_origins_config:
    cors_origins_config = config('CORS_ALLOWED_ORIGINS', default='')

# 处理 CORS 配置：支持字符串（逗号分隔）和列表格式
if isinstance(cors_origins_config, list):
    parsed_cors_origins = cors_origins_config
elif isinstance(cors_origins_config, str):
    parsed_cors_origins = [s.strip() for s in cors_origins_config.split(',') if s.strip()]
else:
    parsed_cors_origins = []

if DEBUG:
    # 开发环境默认允许本地地址，同时合并配置里的地址
    # 优先使用 config.yaml 配置的地址，确保服务器IP优先级最高
    CORS_ALLOWED_ORIGINS = [
        *parsed_cors_origins,  # config.yaml 配置的地址优先
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    # 从 config.yaml 中读取 CORS 配置
    CORS_ALLOW_CREDENTIALS = cors_config.get('allow_credentials', True)
    # 从 config.yaml 中读取允许的请求头
    allowed_headers = cors_config.get('allowed_headers', [])
    # 如果 config.yaml 中没有配置，使用默认值
    if not allowed_headers:
        allowed_headers = [
            'accept',
            'accept-encoding',
            'authorization',
            'content-type',
            'dnt',
            'origin',
            'user-agent',
            'x-csrftoken',
            'x-requested-with',
            'cache-control',  # 添加 SSE 需要的头部
        ]
    CORS_ALLOW_HEADERS = allowed_headers
else:
    # 生产环境 CORS 配置
    if parsed_cors_origins:
        # 如果在 config.yaml 或环境变量中配置了 CORS_ALLOWED_ORIGINS，使用配置的值
        CORS_ALLOWED_ORIGINS = parsed_cors_origins
    else:
        # 如果未配置，允许所有来源（可根据需求调整）
        CORS_ALLOW_ALL_ORIGINS = True

    # 从 config.yaml 中读取 CORS 配置
    CORS_ALLOW_CREDENTIALS = cors_config.get('allow_credentials', True)
    # 从 config.yaml 中读取允许的请求头
    allowed_headers = cors_config.get('allowed_headers', [])
    # 如果 config.yaml 中没有配置，使用默认值
    if not allowed_headers:
        allowed_headers = [
            'accept',
            'accept-encoding',
            'authorization',
            'content-type',
            'dnt',
            'origin',
            'user-agent',
            'x-csrftoken',
            'x-requested-with',
            'cache-control',  # 添加 SSE 需要的头部
        ]
    CORS_ALLOW_HEADERS = allowed_headers
    # SSE 需要的额外配置
    CORS_EXPOSE_HEADERS = ['Content-Type', 'Cache-Control']

# CSRF Settings
CSRF_TRUSTED_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
]

# Security Settings (Django 6 安全特性)
if not DEBUG:
    # 内容安全策略 (CSP)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'

    # SSL/HTTPS 配置
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Session 安全
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # 密码哈希改进 (Django 6)
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.PBKDF2PasswordHasher',
        'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
        'django.contrib.auth.hashers.Argon2PasswordHasher',
    ]

# Data Upload Settings - 增加最大字段数限制
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

# Spectacular Settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'TestHub API',
    'DESCRIPTION': 'Test Case Management Platform API',
    'VERSION': '1.0.3',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}

# Redis配置，开发环境和生产环境都使用配置的Redis
redis_config = config_loader.get_redis_config()
REDIS_URL = config('REDIS_URL', default=redis_config.get('url', 'redis://127.0.0.1:6379/'))
REDIS_DB = config('REDIS_DB', default=redis_config.get('redis_db', 0), cast=int)
REDIS_CACHE_DB = config('REDIS_CACHE_DB', default=redis_config.get('cache_db', 1), cast=int)
REDIS_SESSION_DB = config('REDIS_SESSION_DB', default=redis_config.get('session_db', 2), cast=int)

# 从Redis URL中提取基础URL（去掉末尾的数据库编号）
def get_redis_base_url(url):
    """从Redis URL中提取基础URL"""
    if url.endswith('/'):
        return url
    last_slash = url.rfind('/')
    if last_slash > 0:
        return url[:last_slash + 1]
    return url

REDIS_BASE_URL = get_redis_base_url(REDIS_URL)

# 缓存Redis配置（使用config.yaml中的cache_db）
REDIS_CACHE_URL = f"{REDIS_BASE_URL}{REDIS_CACHE_DB}"

# 会话Redis配置（使用config.yaml中的session_db）
REDIS_SESSION_URL = f"{REDIS_BASE_URL}{REDIS_SESSION_DB}"

# Session配置：使用Redis存储会话（通过sessions缓存）
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'sessions'

# Channels Configuration - 统一使用config.yaml中的Redis配置
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [f"{REDIS_BASE_URL}{REDIS_DB}"],
        },
    },
}

# Cache配置，使用 Redis 缓存（生产环境推荐）
cache_config = config_loader.get_cache_config()

# 任务队列配置
Q_CLUSTER = {
    'name': 'testhub',
    'workers': 1,  # 工作进程数，根据服务器配置做调整
    'timeout': 90,  # 任务超时时间（秒）
    'retry': 32_460,  # 必须覆盖 API 自动化任务最长 9 小时预算，防止执行中被重复投递
    'queue_limit': 50,  # 队列限制
    'bulk': 10,  # 批量处理数量
    'orm': 'default',  # 数据库配置
    'save_limit': 250,  # 保存限制
    'cpu_affinity': 1,  # CPU 亲和性
    'label': '任务管理',  # 菜单名称
    'redis': f"{REDIS_BASE_URL}{REDIS_DB}",  # Redis 配置
    'sync': False,  # False异步模式，True同步模式
}

if DEBUG:
    # 开发环境使用本地内存缓存
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
            'KEY_PREFIX': cache_config.get('key_prefix', 'testhub'),
            'TIMEOUT': cache_config.get('default_timeout', 300),
        },
        'sessions': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake-sessions',
            'KEY_PREFIX': 'session',
            'TIMEOUT': 604800,  # 7天（秒）
        },
    }
else:
    # 生产环境使用Redis（Django 6 内置）
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_CACHE_URL,
            'KEY_PREFIX': cache_config.get('key_prefix', 'testhub'),
            'TIMEOUT': cache_config.get('default_timeout', 300),
            # Django 6 内置 Redis 配置
            'OPTIONS': {
                'socket_connect_timeout': 5,
                'socket_timeout': 5,
                'retry_on_timeout': True,
                'health_check_interval': 30,
            },
        },
        'sessions': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_SESSION_URL,
            'KEY_PREFIX': 'session',
            'TIMEOUT': 604800,  # 7天（秒）
            'OPTIONS': {
                'socket_connect_timeout': 5,
                'socket_timeout': 5,
                'retry_on_timeout': True,
                'health_check_interval': 30,
            },
        },
    }


# Email Configuration
email_config = config_loader.get_email_config()
EMAIL_BACKEND = 'apps.api_testing.custom_email_backend.CustomEmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default=email_config.get('host', 'smtp.gmail.com'))
EMAIL_PORT = config('EMAIL_PORT', default=email_config.get('port', 587), cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=email_config.get('use_tls', True), cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=email_config.get('use_ssl', False), cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default=email_config.get('host_user', ''))
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default=email_config.get('host_password', ''))
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=email_config.get('default_from_email', 'webmaster@localhost'))
EMAIL_TIMEOUT = email_config.get('timeout', 30)

# 读取日志配置
logging_config = config_loader.get_logging_config()
debug_enabled = logging_config.get('debug_enabled', False)
console_level = 'DEBUG' if debug_enabled else 'INFO'
API_AUTOMATION_LOG_MAX_BYTES = 10 * 1024 * 1024
API_AUTOMATION_LOG_FILE = BASE_DIR / 'logs' / 'api_automation.log'

# Logging - 使用log_config.py统一配置
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': console_level,
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'api_automation_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': API_AUTOMATION_LOG_FILE,
            'maxBytes': API_AUTOMATION_LOG_MAX_BYTES,
            'backupCount': 5,
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # 其他具体模块的 logger 配置
        'django': {
            'handlers': ['console'],
            'level': 'DEBUG' if debug_enabled else 'INFO',
            'propagate': True,
        },
        'apps.api_testing.views': {
            'handlers': ['console'],
            'level': 'DEBUG' if debug_enabled else 'INFO',
            'propagate': True,
        },
        'apps.data_factory.tools.json_tools': {
            'handlers': ['console'],
            'level': 'DEBUG' if debug_enabled else 'INFO',
            'propagate': False,
        },
        'apps.data_factory.tools.encoding_tools': {
            'handlers': ['console'],
            'level': 'DEBUG' if debug_enabled else 'INFO',
            'propagate': False,
        },
        'apps.scheduler.task_executor': {
            'handlers': ['console'],
            'level': 'DEBUG' if debug_enabled else 'INFO',
            'propagate': False,
        },
        'apps.api_automation': {
            'handlers': ['console', 'api_automation_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    if hasattr(handler, 'loguru_logger'):
        root_logger.removeHandler(handler)

# 指定simpleui默认的主题,指定一个文件名，相对路径就从simpleui的theme目录读取
SIMPLEUI_DEFAULT_THEME = 'admin.lte.css'
# 是否显示图标
SIMPLEUI_DEFAULT_ICON = True
# 是否关闭登录页粒子效果
SIMPLEUI_LOGIN_PARTICLES = True
# 后台管理首页，可以是url或者html文件
# SIMPLEUI_HOME_PAGE = 'https://www.baidu.com/'  # 后面可以扩展为大屏显示做统计
# 自定义首页标题
# SIMPLEUI_HOME_TITLE = 'Dashboard'
# # 自定义首页图标 首页图标,支持element-ui和fontawesome的图标，参考https://fontawesome.com/icons图标
# SIMPLEUI_HOME_ICON = 'fa fa-gauge'
# 设置simpleui 点击首页图标跳转的地址
SIMPLEUI_INDEX = 'http://localhost:3000'
# 自定义后台的Logo
SIMPLEUI_LOGO = 'https://static.djangoproject.com/img/favicon.6dbf28c0650e.ico'
# 是否显示首页信息
SIMPLEUI_HOME_INFO = False
# 是否显示快捷入口
SIMPLEUI_HOME_QUICK = True
# 是否显示最近动作
SIMPLEUI_HOME_ACTION = True
# 使用分析
SIMPLEUI_ANALYSIS = False
# 离线模式 - 暂时禁用以使用在线资源
SIMPLEUI_STATIC_OFFLINE = True
# True或None 默认显示加载遮罩层，指定为False 不显示遮罩层。默认显示
SIMPLEUI_LOADING = True
# 设置菜单icon，参考https://element.eleme.cn/#/zh-CN/component/icon
SIMPLEUI_ICON = {
    # 一级菜单项
    '测试执行管理': 'el-icon-s-tools',
    '用户管理': 'el-icon-user-solid',
    '令牌黑名单': 'el-icon-warning-outline',
    '接口测试': 'el-icon-s-platform',
    '智能助手': 'el-icon-chat-dot-round',
    '用例评审管理': 'el-icon-edit-outline',
    '认证令牌': 'el-icon-key',
    '认证和授权': 'el-icon-s-check',
    '需求分析': 'el-icon-notebook-2',

    # 二级菜单项
    '测试执行': 'el-icon-s-operation',
    '测试执行历史': 'el-icon-time',
    '测试执行用例': 'el-icon-document',
    '测试计划': 'el-icon-document-checked',
    '用户': 'el-icon-user',
    '用户配置': 'el-icon-setting',
    'Blacklisted Tokens': 'el-icon-warning-outline',
    'Outstanding Tokens': 'el-icon-s-custom',
    'API请求': 'el-icon-s-promotion',
    'API集合': 'el-icon-s-grid',
    'API项目': 'el-icon-s-custom',
    '任务执行日志': 'el-icon-s-data',
    '定时任务': 'el-icon-time',
    '测试套件': 'el-icon-suitcase',
    '环境变量': 'el-icon-school',
    '请求历史': 'el-icon-odometer',
    '智能助手会话': 'el-icon-chat-dot-round',
    '智能助手消息': 'el-icon-message',
    '测试用例评审': 'el-icon-check',
    '评审分配': 'el-icon-guide',
    '评审意见': 'el-icon-s-custom',
    '评审模板': 'el-icon-document',
    'Tokens': 'el-icon-key',
    '组': 'el-icon-s-custom',
    '业务需求': 'el-icon-document-checked',
    '分析任务': 'el-icon-stopwatch',
    '生成的测试用例': 'el-icon-document',
    '需求文档': 'el-icon-document',
}

# 开发环境，暂时禁用迁移历史检查
# SILENCED_SYSTEM_CHECKS = ['django.db.migrations.InconsistentMigrationHistory']
