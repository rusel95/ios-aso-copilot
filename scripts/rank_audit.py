#!/usr/bin/env python3
"""
rank_audit.py — App Store keyword discovery observations with explicit provenance.

Keyword discovery strategy (in order of preference):
  1. --expand-from-hints  : auto-generate queries from Apple's own autocomplete for seed terms
                            This is the RIGHT approach — keywords come from what users actually type.
  2. --keywords "a,b,c"   : manual override for specific terms
  3. DEFAULT_SEEDS + hints : falls back to seeded expansion if no override given

Market-proportional query budgets (bigger market = more queries):
  weight ≥ 50 (US, JP, CN)             : 80–100 queries
  weight 20–49 (DE, GB, FR, KR, IT, …) : 40–60 queries
  weight 10–19 (BR, RU, NL, MX, IN, …) : 25–40 queries
  weight < 10  (UA, SA, IL, SE, …)      : 15–20 queries

Usage:
    # Full auto — uses Apple hints to generate queries, proportional per market
    python3 rank_audit.py --bundle "ruslan.whiteNoise.WhiteNoise" --markets all

    # Specific markets with hint expansion
    python3 rank_audit.py --bundle "com.app.id" --markets us,de --expand-from-hints

    # Manual keyword list (bypass hint expansion)
    python3 rank_audit.py --bundle "com.app.id" --markets us --keywords "white noise,sleep sounds"

    # Save report
    python3 rank_audit.py --bundle "ruslan.whiteNoise.WhiteNoise" --markets all \\
        --output marketing/reports/aso_rank_audit_$(date +%Y-%m-%d).md

    # Test API connectivity
    python3 rank_audit.py --self-check

Opportunity score formula:
    market_weight × volume_proxy × rank_reachability × (1 − difficulty / 130)
    - market_weight    : iOS install/revenue size, US=100 (see MARKET_WEIGHT)
    - volume_proxy     : log-scaled total search results (0–100)
    - rank_reachability: 1.0 if #1–10, 0.7 if #11–20, … 0.005 if absent
    - difficulty       : log-scaled top-1 competitor rating count (0–100)
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# ── Market configuration ──────────────────────────────────────────────────────

MARKET_WEIGHT: dict[str, float] = {
    "us": 100, "jp": 22,  "cn": 30,  "gb": 14,  "de": 13,
    "fr": 10,  "kr": 8,   "in": 8,   "au": 7,   "ca": 7,
    "es": 7,   "it": 7,   "br": 7,   "ru": 5,   "tw": 5,
    "mx": 5,   "nl": 4,   "tr": 4,   "pl": 4,   "sa": 4,
    "se": 3,   "hk": 3,   "sg": 3,   "ua": 2,   "il": 2,
}

# Apple storefront header values for autocomplete hints endpoint
STOREFRONTS: dict[str, str] = {
    "us": "143441-1,29", "gb": "143444-1,29", "de": "143443-1,29",
    "fr": "143442-1,29", "jp": "143462-1,29", "kr": "143466-1,29",
    "cn": "143465-1,29", "tw": "143470-1,29", "br": "143503-1,29",
    "ru": "143469-1,29", "ua": "143492-1,29", "es": "143454-1,29",
    "mx": "143468-1,29", "it": "143450-1,29", "pl": "143478-1,29",
    "nl": "143452-1,29", "se": "143456-1,29", "tr": "143480-1,29",
    "in": "143467-1,29", "sa": "143479-1,29", "il": "143491-1,29",
    "au": "143460-1,29", "ca": "143455-1,29", "sg": "143464-1,29",
    "hk": "143463-1,29",
}

FLAGS: dict[str, str] = {
    "us":"🇺🇸","gb":"🇬🇧","de":"🇩🇪","fr":"🇫🇷","jp":"🇯🇵","kr":"🇰🇷",
    "cn":"🇨🇳","tw":"🇹🇼","br":"🇧🇷","ru":"🇷🇺","ua":"🇺🇦","es":"🇪🇸",
    "mx":"🇲🇽","it":"🇮🇹","pl":"🇵🇱","nl":"🇳🇱","se":"🇸🇪","tr":"🇹🇷",
    "in":"🇮🇳","sa":"🇸🇦","il":"🇮🇱","au":"🇦🇺","ca":"🇨🇦","sg":"🇸🇬",
    "hk":"🇭🇰",
}

ALL_MARKETS = list(MARKET_WEIGHT.keys())

# ── Seed terms per market (used as starting points for hint expansion) ─────────
# These are NOT the full keyword list — they seed Apple autocomplete to discover
# what users actually search for. harvest_keywords.py expands them.
SEED_TERMS: dict[str, list[str]] = {
    "us": ["white noise", "sleep sounds", "brown noise", "rain sounds",
           "nature sounds", "baby sleep", "ambient sounds", "focus sounds"],
    "gb": ["white noise", "sleep sounds", "brown noise", "rain sounds", "baby sleep"],
    "de": ["weißes rauschen", "braunes rauschen", "schlafgeräusche", "naturgeräusche", "regengeräusche"],
    "fr": ["bruit blanc", "bruit brun", "sons pour dormir", "sons de pluie", "sons nature"],
    "jp": ["ホワイトノイズ", "睡眠音楽", "自然音", "雨音"],
    "kr": ["백색소음", "수면 소리", "빗소리", "자연 소리"],
    "cn": ["白噪声", "睡眠音乐", "自然声音", "助眠"],
    "tw": ["白噪音", "睡眠音樂", "自然聲音"],
    "br": ["ruído branco", "sons para dormir", "sons da natureza", "sons da chuva"],
    "ru": ["белый шум", "звуки для сна", "звуки природы", "шум дождя"],
    "ua": ["білий шум", "коричневий шум", "звуки для сну", "шум дощу", "звуки природи"],
    "es": ["ruido blanco", "sonidos para dormir", "sonidos de lluvia", "ruido marrón"],
    "mx": ["ruido blanco", "sonidos para dormir", "sonidos relajantes"],
    "it": ["rumore bianco", "suoni per dormire", "suoni natura"],
    "pl": ["biały szum", "dźwięki do snu", "dźwięki natury"],
    "nl": ["witte ruis", "bruine ruis", "slaapgeluiden", "natuurgeluiden"],
    "se": ["vitt brus", "sovljud", "naturljud"],
    "tr": ["beyaz gürültü", "uyku sesleri", "doğa sesleri"],
    "in": ["white noise", "sleep sounds", "rain sounds", "baby sleep"],
    "sa": ["ضوضاء بيضاء", "أصوات النوم", "أصوات الطبيعة"],
    "il": ["רעש לבן", "צלילים לשינה", "צלילי טבע"],
    "au": ["white noise", "brown noise", "sleep sounds", "rain sounds", "nature sounds"],
    "ca": ["white noise", "sleep sounds", "brown noise", "baby sleep sounds"],
    "sg": ["white noise", "sleep sounds", "nature sounds"],
    "hk": ["白噪音", "睡眠音樂", "自然聲音"],
}

BABY_SEED_TERMS: dict[str, list[str]] = {
    "us": ["baby tracker", "newborn tracker", "baby log", "breastfeeding tracker", "baby feeding", "baby sleep tracker", "diaper tracker", "baby routine"],
    "gb": ["baby tracker", "newborn tracker", "baby log", "breastfeeding tracker", "nappy tracker", "baby sleep tracker"],
    "de": ["baby tracker", "baby schlaf", "stillen tracker", "baby füttern", "baby tagebuch", "baby log"],
    "fr": ["suivi bebe", "bebe tracker", "allaitement tracker", "sommeil bebe", "journal bebe"],
    "jp": ["授乳記録", "育児記録", "赤ちゃん 睡眠", "ベビートラッカー", "授乳タイマー"],
    "kr": ["아기 수면", "수유 기록", "육아 일기", "베이비 트래커", "아기 성장"],
    "cn": ["宝宝记录", "喂奶记录", "母乳喂养", "婴儿睡眠", "宝宝日记"],
    "tw": ["寶寶記錄", "母乳餵養", "嬰兒睡眠", "寶寶日記", "育兒記錄"],
    "br": ["amamentação", "sono do bebe", "fraldas bebe", "rotina do bebe", "baby tracker"],
    "ru": ["трекер малыша", "дневник малыша", "кормление ребенка", "сон ребенка", "грудное вскармливание"],
    "ua": ["трекер малюка", "щоденник малюка", "годування дитини", "трекер годування", "сон дитини", "малятко", "baby tracker", "baby log"],
    "es": ["seguimiento bebe", "bebe tracker", "lactancia materna", "sueño bebe", "pañales bebe"],
    "mx": ["seguimiento bebe", "bebe tracker", "lactancia materna", "sueño bebe", "registro bebe"],
    "it": ["baby tracker", "allattamento", "sonno neonato", "diario neonato", "crescita neonato"],
    "pl": ["baby tracker", "karmienie piersią", "sen dziecka", "dziennik dziecka", "rozwój dziecka"],
    "nl": ["baby tracker", "borstvoeding", "baby slaap", "baby logboek", "baby dagboek"],
    "se": ["baby tracker", "amma tracker", "sova bebis", "bebis app"],
    "tr": ["bebek takip", "bebek emzirme", "bebek uyku", "bebek günlüğü"],
    "in": ["baby tracker", "newborn tracker", "breastfeeding tracker", "baby sleep", "baby log"],
    "sa": ["متتبع الطفل", "تتبع الرضاعة", "نوم الرضيع", "يوميات الطفل"],
    "il": ["מעקב תינוק", "מעקב הנקה", "שינת תינוק", "יומן תינוק"],
    "au": ["baby tracker", "newborn tracker", "baby log", "breastfeeding tracker", "nappy tracker", "baby sleep"],
    "ca": ["baby tracker", "newborn tracker", "baby log", "breastfeeding tracker", "baby feeding", "baby sleep"],
    "sg": ["baby tracker", "newborn tracker", "baby log", "breastfeeding tracker"],
    "hk": ["寶寶記錄", "母乳餵養", "嬰兒睡眠", "baby tracker"],
}

COMPRESS_SEED_TERMS: dict[str, list[str]] = {
    "us": ["compresso", "compress video", "compress photo", "shrink video", "shrink photo", "video compressor", "photo compressor", "free up storage", "reduce video size", "clean storage", "storage cleaner"],
    "gb": ["compresso", "compress video", "compress photo", "shrink video", "shrink photo", "video compressor", "photo compressor", "free up storage", "storage cleaner"],
    "ca": ["compresso", "compress video", "compress photo", "shrink video", "video compressor", "photo compressor", "reduce video size", "storage cleaner"],
    "au": ["compresso", "compress video", "compress photo", "shrink video", "video compressor", "photo compressor", "free up storage", "storage cleaner"],
    "de": ["compresso", "video komprimieren", "foto komprimieren", "video verkleinern", "fotos verkleinern", "speicherplatz bereinigen", "video kompressor", "speicher voll"],
    "fr": ["compresso", "compresser video", "compresser photo", "reduire taille video", "liberer espace", "nettoyer stockage", "compresseur video"],
    "es": ["compresso", "comprimir video", "comprimir fotos", "reducir tamaño video", "compresor de video", "liberar espacio", "limpiar almacenamiento", "reducir fotos"],
    "mx": ["compresso", "comprimir video", "comprimir fotos", "reducir tamaño video", "compresor de video", "liberar espacio", "limpiar almacenamiento"],
    "it": ["compresso", "comprimere video", "comprimere foto", "ridurre dimensioni video", "liberare spazio", "pulizia memoria", "ridurre foto"],
    "pl": ["compresso", "kompresja wideo", "zmniejszanie rozmiaru wideo", "kompresja zdjęć", "czyszczenie pamięci", "zwolnij miejsce", "zmniejsz zdjęcie"],
    "nl": ["compresso", "video comprimeren", "foto comprimeren", "video verkleinen", "opslagruimte vrijmaken", "foto verkleinen", "opslag vol"],
    "ua": ["compresso", "стиснути відео", "стиснення фото", "зменшити розмір відео", "очистити пам'ять", "звільнити місце", "стиснути фото", "очищення пам'яті"],
    "ru": ["compresso", "сжать видео", "сжатие фото", "уменьшить размер видео", "очистить память", "сжатие видео", "освободить место"],
    "br": ["compresso", "comprimir video", "comprimir fotos", "reduzir tamanho video", "liberar espaco", "limpar armazenamento", "compactar video"],
    "tr": ["compresso", "video sıkıştırma", "fotoğraf sıkıştırma", "video boyut küçültme", "hafıza temizleme", "yer açма"],
    "jp": ["compresso", "動画 圧縮", "写真 圧縮", "容量 削減", "動画 サイズ 縮小", "ストレージ 整理", "画像 圧縮"],
    "kr": ["compresso", "동영상 압축", "사진 압축", "용량 줄이기", "동영상 용량", "저장공간 정리"],
    "cn": ["compresso", "视频压缩", "照片压缩", "清理内存", "缩小视频", "释放空间", "压缩图片"],
    "tw": ["compresso", "影片壓縮", "照片壓縮", "清理記憶體", "縮小影片", "釋放空間", "壓縮圖片"],
    "hk": ["compresso", "影片壓縮", "照片壓縮", "清理空間", "縮小影片", "釋放空間"],
    "se": ["compresso", "komprimera video", "förminska video", "rensa minne", "spara utrymme"],
    "in": ["compresso", "compress video", "compress photo", "video compressor", "reduce video size", "clear storage"],
    "sa": ["compresso", "ضغط الفيديو", "ضغط الصور", "تقليل حجم الفيديو", "تنظيف الذاكرة", "تفريغ مساحة"],
    "il": ["compresso", "דחיסת וידاو", "דחיסת תמונות", "פינוי מקום", "ניקוי זיכרון"],
    "sg": ["compresso", "compress video", "compress photo", "shrink video", "video compressor", "storage cleaner"],
}

# Fallback keyword lists when hint expansion fails or is skipped.
# Deliberately INCOMPLETE — the right path is hint expansion, not manual lists.
# Sized proportionally to market weight.
FALLBACK_KEYWORDS: dict[str, list[str]] = {
    "us": [
        "white noise", "sleep sounds", "brown noise", "pink noise",
        "rain sounds", "nature sounds", "baby sleep sounds", "sound machine",
        "ambient sounds", "focus sounds", "thunderstorm sounds", "fan noise",
        "ocean sounds", "sleep music", "meditation sounds", "relaxing sounds",
        "fireplace sounds", "sleep timer", "noise machine", "deep sleep sounds",
        "white noise machine app", "sleep aid app", "calming sounds",
        "white noise for studying", "white noise baby sleep", "brown noise sleep",
        "rain sounds for sleeping", "nature sounds sleep", "ocean waves sleep",
        "thunder sounds sleep", "waterfall sounds", "forest sounds",
        "fan white noise", "airplane noise", "vacuum cleaner noise",
        "static noise", "frequency sounds", "binaural beats sleep",
        "asmr sounds sleep", "sleep noise app", "white noise ipad",
        "sleep sound machine", "spa music", "zen sounds",
        "sleep sounds for adults", "relax melodies", "calm sounds for sleep",
        "rain sounds app", "white noise lite", "sleep noise generator",
        "nature sounds relax", "sleep with noise", "baby white noise machine",
        "sleep sounds baby", "lullaby sounds", "infant sleep sounds",
        "newborn sleep sounds", "baby calm sounds", "sleep aid baby",
        "toddler sleep sounds", "womb sounds", "heartbeat sounds baby",
        "pink noise baby", "brown noise baby", "sleep timer app",
        "sleep countdown", "bedtime timer", "night sounds",
        "sleep aid app free", "free white noise", "sleep relaxation",
        "delta waves sleep", "theta waves sleep", "alpha waves sleep",
        "432hz sleep", "528hz sleep", "solfeggio frequencies sleep",
        "deep sleep music", "sleep hypnosis sounds", "guided sleep sounds",
        "campfire sounds", "cabin sounds", "cozy sounds",
        "coffee shop ambient", "cafe background noise", "study sounds",
        "lo fi sleep", "background noise focus", "concentration sounds",
    ],
    "jp": [
        "ホワイトノイズ", "睡眠音楽", "雨音 睡眠", "自然音",
        "環境音", "ホワイトノイズ 赤ちゃん", "眠れる音楽", "ヒーリング音楽",
        "川の音", "波の音", "焚き火 音", "雷雨 音",
        "ブラウンノイズ", "ピンクノイズ", "カフェ 環境音",
        "集中 音楽", "瞑想 音楽", "自然音 癒し",
        "睡眠 アプリ", "赤ちゃん 寝かしつけ 音",
        "森の音", "鳥 鳴き声 睡眠", "滝の音", "風の音",
        "暖炉の音", "ホワイトノイズ 集中", "αwave 睡眠",
        "深い眠り 音楽", "ストレス解消 音楽", "リラックス 自然音",
        "雨音 赤ちゃん", "うみの音", "夜の音", "春の音",
        "睡眠改善 アプリ", "快眠 アプリ", "白色雑音",
        "ゆっくり眠る", "安眠 音楽", "眠れない 音楽",
    ],
    "cn": [
        "白噪声", "睡眠音乐", "自然声音", "雨声助眠",
        "白噪音", "助眠声音", "棕色噪音", "粉红噪音",
        "冥想音乐", "波浪声", "篝火声", "雷雨声",
        "婴儿睡眠声", "专注白噪声", "咖啡厅背景音",
        "鸟鸣声", "森林声音", "流水声", "助眠app", "放松音乐",
        "深度睡眠音乐", "睡前音乐", "风声助眠", "海浪声",
        "α波助眠", "白噪音app", "专注音乐", "雨声app",
    ],
    "de": [
        "weißes rauschen", "schlafgeräusche", "einschlafhilfe",
        "regengeräusche", "naturgeräusche", "weißes rauschen baby",
        "entspannungsmusik", "schlaf app", "schlafmusik", "braunes rauschen",
        "meeresrauschen", "vogelgeräusche", "meditationsgeräusche",
        "baby einschlafen geräusche", "weißes rauschen fan",
        "naturklänge", "wassergeräusche", "kamingeräusche",
        "gewitter geräusche", "windgeräusche",
        "regen schlafen", "wald geräusche", "entspannungsgeräusche",
        "rosa rauschen", "schlaf geräusche baby", "weißes rauschen schlaf",
        "naturgeräusche baby", "einschlafen musik", "tiefschlaf geräusche",
        "braunes rauschen schlaf", "weißes rauschen kostenlos",
        "beruhigende geräusche", "tiefenentspannung geräusche",
        "natur klänge baby", "schlafmusik baby", "weißes rauschen kind",
        "regengeräusche schlaf", "meeresgeräusche schlaf",
        "schlafstörungen app", "einschlafgeräusche erwachsene",
        "fokus geräusche", "lerngeräusche", "büro geräusche",
    ],
    "gb": [
        "white noise", "sleep sounds", "rain sounds", "nature sounds",
        "baby sleep sounds", "relaxing sounds", "sound machine", "brown noise",
        "pink noise", "fan noise", "sleep music", "calm sounds",
        "ambient sounds", "ocean sounds", "white noise machine",
        "meditation sounds", "thunderstorm sounds", "sleep aid",
        "fireplace sounds", "focus sounds",
        "white noise baby sleep", "brown noise sleep", "sleep timer",
        "rain for sleep", "nature sounds sleep", "sleep app uk",
        "baby white noise", "deep sleep sounds", "calming sounds",
        "sleep sounds free", "rain noise", "wind sounds sleep",
        "forest sounds sleep", "waterfall sounds", "ocean waves sleep",
        "thunderstorm sleep", "sleep relaxation", "bedtime sounds",
        "sleep sounds baby", "sleep aid sounds",
    ],
    "fr": [
        "bruit blanc", "sons pour dormir", "sons de pluie",
        "sons de la nature", "aide au sommeil", "bruit rose",
        "sons relaxants", "bruit brun", "sons de l'océan",
        "musique pour dormir", "sons de meditation", "bruit de ventilateur",
        "sons de feu de cheminée", "sons d'orage", "sons pour bébé",
        "sons d'ambiance", "minuterie sommeil", "bruit blanc bébé",
        "sons de rivière", "sons de forêt",
        "sons de vagues", "relaxation sons", "sommeil profond sons",
        "sons zen", "bruit blanc dormir", "sons pluie dormir",
        "sons naturels", "bruits pour bébé dormir",
        "sons pour se concentrer", "bruits bureau",
        "bruit blanc gratuit", "application sommeil",
        "sons de la nuit", "oiseaux sons", "vent sons",
        "sons zen bébé", "sophrologie sons", "meditation pleine conscience",
        "bruits de fond travail", "concentration musique",
    ],
    "kr": [
        "백색소음", "수면 소리", "빗소리", "자연 소리",
        "집중 소음", "수면 앱", "갈색소음", "분홍소음",
        "파도소리", "모닥불 소리", "천둥소리", "바람소리",
        "태어난 아기 수면", "명상 음악", "카페 소음",
        "빗소리 수면", "폭포 소리", "새소리", "숲소리", "심해 소음",
        "아기 백색소음", "아기 수면 소리", "자장가 소리",
        "수면음악", "집중력 향상 소리", "공부 소리",
    ],
    "br": [
        "ruído branco", "sons para dormir", "sons da chuva",
        "sons da natureza", "ruído rosa", "sons para bebê",
        "ruído marrom", "sons do oceano", "sons da fogueira",
        "sons de trovão", "músicas para dormir", "sons relaxantes",
        "meditação sons", "sons de ventilador", "sons de floresta",
        "sons de rio", "sons do vento", "chuva para dormir",
        "cronômetro de sono", "barulho branco bebê",
        "sons para se concentrar", "sons de fundo trabalho",
        "ruído branco grátis", "ruído branco app",
        "sons de passarinho", "chuva dormir app",
    ],
    "ru": [
        "белый шум", "звуки для сна", "звуки природы",
        "шум дождя", "розовый шум", "звуки для медитации",
        "коричневый шум", "звуки леса", "шум моря",
        "звуки костра", "шум грозы", "звуки для малышей",
        "шум вентилятора", "звуки реки", "звуки птиц",
        "музыка для сна", "таймер сна", "звуки кафе",
        "белый шум для детей", "расслабляющие звуки",
        "белый шум бесплатно", "фоновые звуки работа",
        "звуки для концентрации", "шум дождя для сна",
        "природные звуки для сна",
    ],
    "ua": [
        "білий шум", "звуки для сну", "шум дощу",
        "звуки природи", "коричневий шум", "шум вентилятора",
        "музика для сну", "рожевий шум", "звуки лісу",
        "шум моря", "звуки вогнища", "шум грози",
        "звуки для дітей", "звуки річки", "спів птахів",
        "таймер сну", "медитація звуки", "розслаблюючі звуки",
        "звуки кафе", "шум вітру",
    ],
    "es": [
        "ruido blanco", "sonidos para dormir", "sonidos de lluvia",
        "ruido rosa", "sonidos relajantes", "ruido marrón",
        "sonidos de la naturaleza", "sonidos del mar", "sonidos de fuego",
        "sonidos de tormenta", "música para dormir", "sonidos para bebés",
        "ruido de ventilador", "meditación sonidos", "sonidos de bosque",
        "sonidos de río", "temporizador de sueño", "sonidos de pájaros",
        "ruido blanco bebé", "sonidos de café",
        "sonidos de fondo trabajo", "sonidos para concentrarse",
        "ruido blanco gratis", "sonidos de olas", "sonidos zen",
        "sonidos de lluvia app", "ruido blanco app",
        "sonidos de ballenas", "sonidos de cascada", "sonidos de viento",
        "sonidos nocturnos", "sonidos para relajarse",
        "ruido de lluvia", "audio para dormir",
        "sonidos de naturaleza gratis", "música relajante dormir",
        "meditación app", "sonidos de aves", "sonidos de selva",
        "sonidos para estudiar",
    ],
    "mx": [
        "ruido blanco", "sonidos para dormir", "sonidos de lluvia",
        "ruido rosa", "sonidos relajantes", "ruido marrón",
        "sonidos de la naturaleza", "sonidos del mar", "música para dormir",
        "sonidos para bebés", "meditación sonidos", "ruido ventilador",
        "sonidos bosque", "sonidos tormenta", "temporizador sueño",
        "sonidos río", "ruido blanco bebé", "sonidos fuego",
        "sonidos de café", "pájaros sonidos",
        "sonidos para concentrarse", "ruido blanco gratis",
        "sonidos relajantes gratis", "sonidos de olas",
        "lluvia para dormir",
    ],
    "it": [
        "rumore bianco", "suoni per dormire", "suoni della natura",
        "suoni rilassanti", "rumore rosa", "rumore marrone",
        "suoni della pioggia", "suoni del mare", "musica per dormire",
        "suoni per neonati", "suoni meditazione", "rumore ventilatore",
        "suoni temporale", "suoni fuoco", "suoni bosco",
        "timer sonno", "suoni fiume", "canti degli uccelli",
        "rumore bianco neonato", "suoni caffè",
        "suoni concentrazione", "suoni fondo lavoro",
        "rumore bianco gratis", "suoni onde", "suoni zen",
        "pioggia per dormire", "suoni notte", "suoni vento",
        "suoni cascata", "musica rilassante sonno",
        "meditazione suoni", "suoni balena",
    ],
    "pl": [
        "biały szum", "dźwięki do snu", "dźwięki natury",
        "dźwięki deszczu", "różowy szum", "brązowy szum",
        "dźwięki morza", "dźwięki ognia", "dźwięki burzy",
        "muzyka do snu", "dźwięki dla dzieci", "szum wiatru",
        "dźwięki lasu", "medytacja dźwięki", "szum wentylatora",
        "dźwięki rzeki", "dźwięki ptaków", "timer snu",
        "biały szum dla niemowląt", "dźwięki kawiarni",
        "dźwięki do koncentracji", "szum tła praca",
        "biały szum za darmo", "dźwięki fal",
        "deszcz do snu",
    ],
    "nl": [
        "witte ruis", "slaapgeluiden", "natuurgeluiden",
        "regengeluiden", "roze ruis", "bruine ruis",
        "oceaangeluiden", "vuurgeluiden", "onweersgeluiden",
        "muziek om in te slapen", "geluiden voor baby",
        "ventilatorgeluid", "bosgeluiden", "meditatie geluiden",
        "riviergeluiden", "vogelgeluiden", "slaaptimer",
        "witte ruis baby", "cafégeluiden", "windgeluiden",
        "concentratie geluiden", "achtergrond geluid werk",
        "witte ruis gratis", "golfgeluiden",
        "regen slaap app",
    ],
    "se": [
        "vitt brus", "sovljud", "naturljud",
        "regn ljud", "rosa brus", "brunt brus",
        "havsljud", "eldljud", "åskaljud",
        "musik för att sova", "ljud för baby", "fläktljud",
        "skogsljud", "meditationsljud", "flodljud",
        "fågelljud", "sömnur", "vitt brus baby",
        "kaffehusbakgrundsljud", "vindljud",
    ],
    "tr": [
        "beyaz gürültü", "uyku sesleri", "doğa sesleri",
        "yağmur sesleri", "pembe gürültü", "kahverengi gürültü",
        "deniz sesleri", "ateş sesleri", "fırtına sesleri",
        "uyku müziği", "bebek uyku sesleri", "fan sesi",
        "orman sesleri", "meditasyon sesleri", "nehir sesleri",
        "kuş sesleri", "uyku zamanlayıcı", "beyaz gürültü bebek",
        "kafe sesleri", "rüzgar sesleri",
        "odaklanma sesleri", "arka plan sesi çalışma",
        "beyaz gürültü ücretsiz", "dalga sesleri",
        "yağmur uyku uygulaması",
    ],
    "in": [
        "white noise", "sleep sounds", "rain sounds",
        "nature sounds", "baby sleep sounds", "relaxing sounds",
        "brown noise", "pink noise", "meditation sounds",
        "ambient sounds", "ocean sounds", "sleep music",
        "fan sounds", "thunder sounds", "focus sounds",
        "forest sounds", "sleep timer", "fireplace sounds",
        "river sounds", "bird sounds",
        "white noise baby", "sleep aid sounds",
        "rain sounds sleep", "nature sounds sleep",
        "sleep sounds free",
    ],
    "sa": [
        "ضوضاء بيضاء", "أصوات النوم", "أصوات الطبيعة",
        "أصوات المطر", "ضوضاء وردية", "موسيقى للنوم",
        "أصوات البحر", "أصوات للأطفال", "أصوات التأمل",
        "صوت المروحة", "أصوات الغابة", "أصوات العواصف",
        "أصوات النهر", "أصوات الطيور", "مؤقت النوم",
        "ضوضاء بنية", "أصوات النار", "أصوات الريح",
        "أصوات المحيط", "ضوضاء بيضاء للأطفال",
    ],
    "il": [
        "רעש לבן", "צלילים לשינה", "צלילי טבע",
        "צלילי גשם", "רעש ורוד", "מוסיקה לשינה",
        "צלילי ים", "צלילים לתינוק", "צלילי מדיטציה",
        "רעש מאוורר", "צלילי יער", "צלילי סופה",
        "צלילי נהר", "צלילי ציפורים", "טיימר שינה",
        "רעש חום", "צלילי אש", "צלילי רוח",
        "צלילי אוקיינוס", "רעש לבן לתינוקות",
    ],
    "au": [
        "white noise", "sleep sounds", "rain sounds", "nature sounds",
        "baby sleep sounds", "relaxing sounds", "brown noise", "pink noise",
        "ocean sounds", "sleep music", "ambient sounds", "fan noise",
        "thunderstorm sounds", "meditation sounds", "sleep timer",
        "forest sounds", "fireplace sounds", "focus sounds",
        "white noise baby", "calm sounds",
        "sleep sounds free", "nature sounds sleep",
        "rain sounds app", "sleep aid sounds",
        "deep sleep sounds",
    ],
    "ca": [
        "white noise", "sleep sounds", "brown noise", "pink noise",
        "rain sounds", "nature sounds", "baby sleep sounds", "sound machine",
        "ambient sounds", "focus sounds", "ocean sounds", "sleep music",
        "thunderstorm sounds", "fan noise", "sleep timer",
        "forest sounds", "fireplace sounds", "relaxing sounds",
        "white noise baby", "meditation sounds",
        "sleep aid sounds", "deep sleep sounds",
        "rain sounds sleep", "white noise machine",
        "calm sounds",
    ],
    "sg": [
        "white noise", "sleep sounds", "nature sounds",
        "rain sounds", "baby sleep sounds", "brown noise",
        "ambient sounds", "ocean sounds", "sleep music",
        "meditation sounds", "relaxing sounds", "fan sounds",
        "thunderstorm sounds", "focus sounds", "sleep timer",
    ],
    "hk": [
        "白噪音", "睡眠音樂", "自然聲音",
        "雨聲助眠", "棕色噪音", "粉紅噪音",
        "冥想音樂", "海浪聲", "篝火聲",
        "雷雨聲", "嬰兒睡眠聲", "森林聲音",
        "流水聲", "鳥鳴聲", "放鬆音樂",
    ],
}


def _query_budget(country: str) -> int:
    """Return appropriate query count for a market, proportional to its weight."""
    w = MARKET_WEIGHT.get(country, 3)
    if w >= 50:   return 90    # US, JP, CN
    if w >= 20:   return 50    # DE, GB, FR, KR, IT, ES, AU, CA
    if w >= 10:   return 30    # BR, RU, NL, MX, IN, TR, PL
    return 20                  # UA, SA, IL, SE, HK, SG, TW


def _get(url: str, headers: dict | None = None, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_hints(term: str, country: str) -> list[str]:
    """Fetch Apple autocomplete hints for `term` in `country`.
    Returns suggestions for discovery; ordering is not calibrated search volume.
    """
    storefront = STOREFRONTS.get(country)
    if not storefront:
        return []
    url = (
        "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
        f"?clientApplication=Software&term={urllib.parse.quote(term)}"
    )
    try:
        body = _get(url, headers={
            "X-Apple-Store-Front": storefront,
            "User-Agent": "iTunes/12.0 (Macintosh)",
        })
        root = ET.fromstring(body)
        hints_array = root.find("./dict/array")
        if hints_array is None:
            return []
        return [
            d.findtext("string", "")
            for d in hints_array.findall("dict")
            if d.findtext("string")
        ]
    except Exception:
        return []


def expand_keywords(seeds: list[str], country: str, budget: int) -> tuple[list[str], dict[str, int]]:
    """
    Expand seed terms using Apple autocomplete hints.
    Returns deduplicated list of up to `budget` terms, seeds-first,
    along with a dictionary mapping term -> hint_rank (observed suggestion order, not popularity).
    """
    seen: set[str] = set()
    result: list[str] = []
    hint_ranks: dict[str, int] = {}

    def add(term: str, rank: int | None) -> None:
        t = term.strip().lower()
        if t and t not in seen:
            seen.add(t)
            result.append(term.strip())
            hint_ranks[term.strip()] = rank
        elif t and rank is not None:
            canonical = next(x for x in result if x.lower() == t)
            if hint_ranks[canonical] is None:
                hint_ranks[canonical] = rank

    # A supplied seed is not an observed first autocomplete result.
    for s in seeds:
        add(s, None)

    # Level 1: hints for each seed
    level1: list[str] = []
    for seed in seeds:
        hints = fetch_hints(seed, country)
        for i, h in enumerate(hints):
            add(h, i + 1)
            level1.append(h)
        time.sleep(0.2)

    # Level 2: hints for level-1 hints (if budget allows)
    if len(result) < budget:
        for term in level1[:10]:  # limit level-2 expansion to top 10 hints
            if len(result) >= budget:
                break
            for i, h in enumerate(fetch_hints(term, country)):
                add(h, 10 + i + 1)
            time.sleep(0.2)

    return result[:budget], hint_ranks


def search_itunes(term: str, country: str, limit: int = 200) -> list[dict]:
    params = urllib.parse.urlencode({
        "term": term, "country": country,
        "media": "software", "entity": "software", "limit": limit,
    })
    data = json.loads(_get(f"https://itunes.apple.com/search?{params}"))
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Invalid iTunes response: missing results list")
    if any(not isinstance(app, dict) for app in data["results"]):
        raise ValueError("Invalid iTunes result row")
    return data["results"]


def audit_keyword(term: str, country: str, bundle_id: str, hint_rank: int | None = None) -> dict:
    provenance = {"source": "itunes-search-api", "rank_kind": "api_order_proxy",
                  "observed_at": datetime.now(timezone.utc).isoformat(),
                  "bundle_id": bundle_id, "query_limit": 200}
    try:
        results = search_itunes(term, country)
    except (OSError, ValueError, TimeoutError) as exc:
        return {"term": term, "country": country, "hint_rank": hint_rank,
                "our_rank": None, "total_results": None, "query_status": "error",
                "error": f"{type(exc).__name__}: {exc}", **provenance}
    total = len(results)

    our_rank: Optional[int] = None
    for i, app in enumerate(results, 1):
        if app.get("bundleId") == bundle_id:
            our_rank = i
            break

    competitors = [a for a in results[:10] if a.get("bundleId") != bundle_id][:3]
    top1 = competitors[0] if len(competitors) > 0 else {}
    top2 = competitors[1] if len(competitors) > 1 else {}
    top3 = competitors[2] if len(competitors) > 2 else {}

    top3_ratings = [c.get("userRatingCount", 0) for c in competitors]
    top3_avg_ratings = int(sum(top3_ratings) / max(len(top3_ratings), 1))
    top3_names = [c.get("trackName", "") for c in competitors]

    term_words = [w for w in re.sub(r'[^\w\s]', '', term.lower()).split() if len(w) > 1]
    top3_has_title_match = False
    for name in top3_names:
        clean_name = re.sub(r'[^\w\s]', '', name.lower())
        if term.lower() in name.lower() or (term_words and all(w in clean_name for w in term_words)):
            top3_has_title_match = True
            break

    return {
        **provenance,
        "query_status": "ok",
        "term": term,
        "country": country,
        "hint_rank": hint_rank,
        "total_results": total,
        "our_rank": our_rank,
        "top1_name": top1.get("trackName", "?")[:30],
        "top1_ratings_total": top1.get("userRatingCount", 0),
        "top1_ratings_current": top1.get("userRatingCountForCurrentVersion", 0),
        "top1_score": top1.get("averageUserRating", 0.0),
        "top2_name": top2.get("trackName", "?")[:30] if top2 else "—",
        "top2_ratings_total": top2.get("userRatingCount", 0) if top2 else 0,
        "top3_name": top3.get("trackName", "?")[:30] if top3 else "—",
        "top3_ratings_total": top3.get("userRatingCount", 0) if top3 else 0,
        "top3_avg_ratings": top3_avg_ratings,
        "top3_has_title_match": top3_has_title_match,
    }


def compute_scores(row: dict, country: str) -> dict:
    """Retire uncalibrated volume, takeover and ROI scores; keep raw observations."""
    return {"score_kind": "unavailable_without_demand_and_outcome_evidence",
            **{key: None for key in ("volume_proxy", "popularity", "vol_index", "difficulty",
                                    "kei", "top3_score", "asa_score", "opportunity")},
            "strategy": "Validate exact-query demand, relevance and conversion before prioritizing",
            "asa_action": "No spend recommendation from API order or review counts"}


def run_audit(
    bundle_id: str,
    markets: list[str],
    expand_hints: bool = True,
    manual_keywords: Optional[dict[str, list[str]]] = None,
    custom_seeds: Optional[list[str]] = None,
    niche: str = "whitenoise",
    delay: float = 0.35,
) -> dict[str, list[dict]]:
    all_results: dict[str, list[dict]] = {}

    for country in markets:
        w = MARKET_WEIGHT.get(country, 3)
        budget = _query_budget(country)
        flag = FLAGS.get(country, country.upper())

        hint_ranks: dict[str, int] = {}
        if manual_keywords and country in manual_keywords:
            queries = manual_keywords[country][:budget]
            hint_ranks = {q: None for q in queries}
            src = "manual"
        elif expand_hints and country in STOREFRONTS:
            if custom_seeds:
                seeds = custom_seeds
            elif niche == "baby":
                seeds = BABY_SEED_TERMS.get(country, [])
            elif niche in ["compress", "media"]:
                seeds = COMPRESS_SEED_TERMS.get(country, [])
            else:
                seeds = SEED_TERMS.get(country, [])
            print(f"  {flag} {country.upper():3} expanding hints from {len(seeds)} seeds… ", end="", flush=True)
            queries, hint_ranks = expand_keywords(seeds, country, budget)
            src = f"hints({len(queries)})"
        else:
            fallback = FALLBACK_KEYWORDS.get(country, [])
            queries = fallback[:budget]
            hint_ranks = {q: None for q in queries}
            src = f"fallback({len(queries)})"

        print(f"  {flag} {country.upper():3} [{src}] {len(queries)} queries…", end=" ", flush=True)

        rows = []
        for term in queries:
            h_rank = hint_ranks.get(term)
            row = audit_keyword(term, country, bundle_id, hint_rank=h_rank)
            scores = compute_scores(row, country)
            rows.append({**row, **scores})
            time.sleep(delay)

        found = sum(1 for r in rows if r["our_rank"])
        best  = min((r["our_rank"] for r in rows if r["our_rank"]), default=None)
        print(f"{found}/{len(queries)} ranked, best #{best or '—'}")

        all_results[country] = rows

    return all_results


def format_report(bundle_id: str, results: dict[str, list[dict]]) -> str:
    rows = [r for items in results.values() if isinstance(items, list) for r in items]
    errors = sum(r.get("query_status") == "error" for r in rows)
    lines = ["# App Store discovery observations", "",
             f"Bundle: `{bundle_id}`. Report generated: {datetime.now(timezone.utc).isoformat()}.",
             f"Queries: {len(rows)}. Errors: {errors}.", "",
             "Positions are iTunes Search API order, not verified organic device rankings.",
             "Missing provenance in older snapshots stays unverified. Report generation is not a fresh observation.",
             "Review counts, autocomplete order and result counts do not establish demand, competitiveness, ROI or a paid-to-organic lift.",
             "Legacy predictive scores are retired; keyword research needs exact-query evidence.", ""]
    for country, items in sorted(results.items()):
        if not isinstance(items, list):
            continue
        lines += [f"## {country.upper()}", "", "| Query | API position | Status | Observed at | First other result | Ratings |", "|---|---:|---|---|---|---:|"]
        for row in items:
            status = row.get("query_status", "legacy provenance unverified")
            position = row.get("our_rank")
            if status == "error":
                pos = "unknown"
            else:
                pos = str(position) if position is not None else "not observed in returned results"
            cells = [row["term"], pos, status, row.get("observed_at", "unknown"), row.get("top1_name", "unknown"), str(row.get("top1_ratings_total", "unknown"))]
            lines.append("| " + " | ".join(str(x).replace("|", r"\|").replace("\n", " ") for x in cells) + " |")
        lines.append("")
    return "\n".join(lines)


def self_check() -> None:
    from unittest.mock import patch
    with patch(__name__ + "._get", side_effect=TimeoutError("test timeout")):
        failed = audit_keyword("compress photo", "us", "com.test")
        assert failed["query_status"] == "error" and failed["total_results"] is None
    with patch(__name__ + "._get", return_value=b'{"results": []}'):
        absent = audit_keyword("compress photo", "us", "com.test")
        assert absent["query_status"] == "ok" and absent["total_results"] == 0
    with patch(__name__ + ".fetch_hints", return_value=[]), patch(__name__ + ".time.sleep"):
        _, ranks = expand_keywords(["unmeasured seed"], "us", 1)
        assert ranks["unmeasured seed"] is None
    assert compute_scores(absent, "us")["popularity"] is None
    assert "unknown | error" in format_report("com.test", {"us": [failed]})
    print("OK: request errors stay unknown; supplied seeds have no measured popularity; no forecast scores")


def main() -> None:
    p = argparse.ArgumentParser(description="App Store keyword rank + opportunity audit")
    p.add_argument("--bundle", help="Exact app bundle ID; required outside self-check")
    p.add_argument("--markets", default="all",
                   help="Comma-separated codes or 'all'")
    p.add_argument("--expand-from-hints", action="store_true",
                   help="Use Apple autocomplete to generate queries (recommended)")
    p.add_argument("--keywords", default=None,
                   help="Manual comma-separated keywords (bypasses hint expansion)")
    p.add_argument("--seeds", default=None,
                   help="Custom comma-separated seed terms for hint expansion")
    p.add_argument("--niche", default="whitenoise", choices=["whitenoise", "baby", "compress", "media"],
                   help="Seed niche profile (whitenoise, baby, compress, media)")
    p.add_argument("--output",  default=None)
    p.add_argument("--delay",   type=float, default=0.35)
    p.add_argument("--reanalyze", default=None,
                   help="Path to an existing audit JSON file to recompute scores without querying Apple APIs")
    p.add_argument("--self-check", action="store_true")
    args = p.parse_args()

    if args.self_check:
        self_check()
        return

    if not args.bundle:
        p.error("--bundle is required; never infer the app from its name")

    if args.reanalyze:
        json_path = Path(args.reanalyze)
        if not json_path.exists():
            print(f"Error: file not found: {args.reanalyze}", file=sys.stderr)
            sys.exit(1)
        print(f"Re-analyzing existing audit data from: {json_path}")
        with open(json_path) as f:
            results = json.load(f)

        # Re-score all rows across all markets
        for country, rows in results.items():
            if not isinstance(rows, list):
                continue
            for r in rows:
                new_scores = compute_scores(r, country)
                r.update(new_scores)

        out_md_path = Path(args.output) if args.output else json_path.with_suffix(".md")
        out_json_path = out_md_path.with_suffix(".json")

        report = format_report(args.bundle, results)
        out_md_path.write_text(report)
        out_json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"Updated report written → {out_md_path}")
        print(f"Updated JSON written → {out_json_path}")
        return

    markets = ALL_MARKETS if args.markets == "all" else [m.strip() for m in args.markets.split(",")]

    total_q = sum(_query_budget(m) for m in markets)
    print(f"ASO Rank Audit — {args.bundle} [Niche: {args.niche}]")
    print(f"Markets: {', '.join(markets)}  |  Budget: ~{total_q} queries")
    if args.expand_from_hints:
        print("  Mode: Apple autocomplete hint expansion (proportional budgets)\n")
    else:
        print("  Mode: fallback keyword lists (use --expand-from-hints for better coverage)\n")

    manual_kw: Optional[dict] = None
    if args.keywords:
        kws = [k.strip() for k in args.keywords.split(",")]
        manual_kw = {m: kws for m in markets}

    seeds_list: Optional[list[str]] = None
    if args.seeds:
        seeds_list = [s.strip() for s in args.seeds.split(",") if s.strip()]

    results = run_audit(
        args.bundle, markets,
        expand_hints=args.expand_from_hints or (manual_kw is None),
        manual_keywords=manual_kw,
        custom_seeds=seeds_list,
        niche=args.niche,
        delay=args.delay,
    )
    report = format_report(args.bundle, results)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"\nReport → {args.output}")
        # Save structured machine-readable snapshot JSON alongside markdown report
        json_path = out_path.with_suffix(".json")
        json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"Snapshot JSON → {json_path}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()
