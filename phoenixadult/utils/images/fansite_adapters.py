from __future__ import annotations

import re

from phoenixadult.utils.images.fanart import FansiteAdapter, Gallery, register_fansite


def _cls(token: str) -> str:
    """Whitespace-bounded class-token match (CSS `.token` equivalent)."""
    return f'contains(concat(" ", normalize-space(@class), " "), " {token} ")'


def _passion_hd(key: str, display_name: str, search_domain: str, gallery: Gallery) -> FansiteAdapter:
    return FansiteAdapter(
        key=key,
        display_name=display_name,
        search_domain=search_domain,
        header_actor_selectors=(
            f'//div[{_cls("page-title")} and {_cls("pad")} and {_cls("group")}]//a[not(contains(@href,"respond")) and not(contains(@href,"comments"))]',
        ),
        title_selector=f'//h1[{_cls("post-title")}]',
        summary_selector=f'//div[{_cls("entry-inner")}]//p',
        gallery=gallery,
    )


def _spy_fams(key: str, display_name: str, search_domain: str) -> FansiteAdapter:
    return FansiteAdapter(
        key=key,
        display_name=display_name,
        search_domain=search_domain,
        header_actor_selectors=('//span[@itemprop="articleSection" and not(contains(., "Family")) and not(contains(., "Sis Loves Me"))]',),
        title_selector='//h1',
        uncategorized_fallback_selector='//h1',
        gallery=Gallery(selector='//div[contains(@class,"tiled-gallery")]//a//img', attr='data-orig-file'),
    )


_ADAPTERS = [
    FansiteAdapter(
        key='xartfan.com',
        display_name='XartFan.com',
        search_domain='xartfan.com',
        header_actor_selectors=(f'//header[{_cls("entry-header")}]//p//a',),
        title_selector='//h1',
        gallery=Gallery(
            selector='//div[contains(@class,"tiled-gallery")]//a//img',
            attr='data-orig-file',
            transform=lambda url, _page: re.sub(r'^https?://images\.', 'https://', url),
        ),
    ),
    FansiteAdapter(
        key='xartbeauties.com',
        display_name='XartBeauties.com',
        search_domain='xartbeauties.com',
        header_actor_selectors=('//a[contains(@href,"models") and not(contains(., "Models"))]',),
        title_selector=f'//div[@id="header-text"]//p[not({_cls("promo")})]',
        gallery=Gallery(
            selector='//div[@id="gallery-thumbs"]//img',
            attr='src',
            transform=lambda url, _page: url.replace('images.', 'www.').replace('/tn', ''),
        ),
    ),
    FansiteAdapter(
        key='hqsluts.com',
        display_name='HQSluts.com',
        search_domain='hqsluts.com',
        header_actor_selectors=(f'//p[{_cls("details")}]//a[contains(@href,"sluts")]',),
        title_selector=f'//p[{_cls("desc")}]//span',
        gallery=Gallery(selector=f'//li[{_cls("item")} and {_cls("i")}]//a', attr='href'),
    ),
    FansiteAdapter(
        key='imagepost.com',
        display_name='ImagePost.com',
        search_domain='imagepost.com',
        header_actor_selectors=('//h3//a[contains(@href,"star")]', '//h3//strong'),
        title_selector='//h1',
        gallery=Gallery(selector='//div[@id="theGallery"]//a', attr='href'),
        summary_selector=f'//div[{_cls("central-section-content")}]//p',
    ),
    FansiteAdapter(
        key='coedcherry.com',
        display_name='CoedCherry.com',
        search_domain='coedcherry.com',
        header_actor_selectors=(f'//div[{_cls("models")}]//figcaption',),
        gallery=Gallery(selector=f'//div[{_cls("thumbs")}]//a[{_cls("track")}]', attr='href'),
    ),
    FansiteAdapter(
        key='nude-gals.com',
        display_name='Nude-Gals.com',
        search_domain='nude-gals.com',
        header_actor_selectors=(f'//div[{_cls("row")} and {_cls("photoshoot-title")} and {_cls("row_margintop")}]//a[contains(@href,"model")]',),
        title_selector='//h1//small',
        gallery=Gallery(
            selector=f'//div[{_cls("row")} and {_cls("row_margintop")}]//a[not(contains(@title,"#"))]',
            attr='href',
            transform=lambda url, _page: url if url.startswith('http') else f'https://nude-gals.com/{url}',
        ),
    ),
    _passion_hd(
        'passionhdfan.com', 'PassionHDFan.com', 'passionhdfan.com', Gallery(selector='//div[contains(@class,"tiled-gallery")]//a//img', attr='data-orig-file')
    ),
    _passion_hd('tiny4kfan.com', 'Tiny4KFan.com', 'tiny4kfan.com', Gallery(selector='//div[contains(@class,"tiled-gallery")]//a//img', attr='data-orig-file')),
    _passion_hd('analpornfan.com', 'AnalPornFan.com', 'analpornfan.com', Gallery(selector='//div[contains(@class,"rgg-imagegrid")]//a', attr='href')),
    _passion_hd('lubedfan.com', 'LubedFan.com', 'lubedfan.com', Gallery(selector='//div[contains(@class,"rgg-imagegrid")]//a', attr='href')),
    FansiteAdapter(
        key='eroticbeauties.net',
        display_name='EroticBeauties.net',
        search_domain='eroticbeauties.net',
        header_actor_selectors=(f'//div[{_cls("clearfix")}]//a[contains(@href,"model")]',),
        title_selector='//div[contains(@class,"gallery-title")]//h1',
        gallery=Gallery(selector='//div[contains(@class,"my-gallery")]//a', attr='href'),
    ),
    FansiteAdapter(
        key='pinkworld.com',
        display_name='PinkWorld.com',
        search_domain='pinkworld.com',
        header_actor_selectors=(f'//div[{_cls("clearfix")}]//a[contains(@href,"pornstar")]',),
        title_selector='//h1',
        gallery=Gallery(selector='//div[contains(@class,"my-gallery")]//a', attr='href'),
    ),
    FansiteAdapter(
        key='porngirlserotica.com',
        display_name='PornGirlsErotica.com',
        search_domain='porngirlserotica.com',
        header_actor_selectors=(f'//h2[{_cls("title")}]',),
        title_selector=f'//h2[{_cls("title")}]',
        gallery=Gallery(selector=f'//div[{_cls("ngg-galleryoverview")}]//a', attr='href'),
    ),
    FansiteAdapter(
        key='skeetscenes.com',
        display_name='SkeetScenes.com',
        search_domain='skeetscenes.com',
        header_actor_selectors=(f'//div[{_cls("card-body")}]//h1//a[contains(@href,"model")]',),
        title_selector='//h1',
        gallery=Gallery(
            selector=f'//div[{_cls("row")}]/div[contains(@class,"col-xl-2")]//img',
            attr='data-srcset',
            transform=lambda raw, _page: _skeet_transform(raw),
        ),
    ),
    _spy_fams('spyfams.com', 'SpyFams.com', 'spyfams.com'),
    _spy_fams('teamskeetfans.com', 'TeamSkeetFans.com', 'teamskeetfans.com'),
]


def _skeet_transform(raw: str) -> str:
    cleaned = raw.replace('_thumb', '').replace('.webp', '.jpg').strip()
    if not cleaned:
        return cleaned
    if cleaned.startswith('http'):
        return cleaned
    if cleaned.startswith('//'):
        return f'https:{cleaned}'
    return cleaned


for _adapter in _ADAPTERS:
    register_fansite(_adapter)
