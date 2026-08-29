import json
import math
import os
import urllib.request
from typing import List, Dict, Optional, Tuple

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register("maiwhat", "Srylicon with Spark", "舞萌DX单曲Rating推荐插件", "1.0.0")
class MaiWhatPlugin(Star):
    def _load_music_data(self):
        url = "https://www.diving-fish.com/api/maimaidxprober/music_data"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"}) #问就是我自己的UA(xD
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.music_data = json.loads(resp.read().decode("utf-8"))
        with open(self.music_data_file, "w", encoding="utf-8") as f:
                json.dump(self.music_data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _calc_min_ach_for_ra(ds: float, target_ra: int) -> Tuple[Optional[str], Optional[int]]:
        """
        计算达到目标 rating 所需的最低达成度（达成值）
        舞萌 DX Rating 公式：
          - 100.5% (SSS+): floor(ds * 22.4 * 1.005)
          - 100.0% ~ 100.4999% (SSS): floor(ds * 21.6 * (ach / 100))
          - 99.5% ~ 99.9999% (SS+): floor(ds * 21.1 * (ach / 100))
          - 99.0% ~ 99.4999% (SS): floor(ds * 20.8 * (ach / 100))
          - 98.0% ~ 98.9999% (S+): floor(ds * 20.3 * (ach / 100))
          - 97.0% ~ 97.9999% (S): floor(ds * 20.0 * (ach / 100))
        """
        # 标准评级档位（从低到高检查是否达标）
        standard_tiers = [
            (97.0, 20.0),
            (98.0, 20.3),
            (99.0, 20.8),
            (99.5, 21.1),
            (100.0, 21.6),
            (100.5, 22.4),
        ]

        for ach, coeff in standard_tiers:
            if ach == 100.5:
                ra = math.floor(ds * 22.4 * 1.005)
            else:
                ra = math.floor(ds * coeff * (ach / 100.0))
            if ra >= target_ra:
                return f"{ach:.4f}", ra

        # 检查是否在 100.0001% ~ 100.4999% 区间内达到
        if math.floor(ds * 21.6 * 1.004999) >= target_ra:
            req_ach = (target_ra / (ds * 21.6)) * 100.0
            req_ach = math.ceil(req_ach * 10000.0) / 10000.0
            return f"{req_ach:.4f}", target_ra

        # 检查 SSS+ 理论极限
        max_ra = math.floor(ds * 22.4 * 1.005)
        if max_ra >= target_ra:
            return "100.5000", max_ra

        return None, None

    @filter.command("maiwhat")
    async def maiwhat(self, event: AstrMessageEvent, min_ra: str = ""):
        """根据最低单曲Rating推荐曲目，用法：/maiwhat <最低Rating>"""
        if not min_ra.strip():
            yield event.plain_result("💡 请输入目标单曲 Rating，例如：/maiwhat 330")
            return

        try:
            target_ra = int(min_ra.strip())
        except ValueError:
            yield event.plain_result("❌ 请输入有效的数字 Rating，例如：/maiwhat 330")
            return

        if target_ra > 337:
            yield event.plain_result(f"⚠️ 舞萌 DX 当前最高单曲 Rating 理论值为 337（15.0 SSS+），输入的 {target_ra} 超出范围。")
            return

        matched_charts = []
        for song in self.music_data:
            title = song.get("title", "")
            is_dx = song.get("type") == "DX"
            song_name = f"[DX]{title}" if is_dx else title
            ds_list = song.get("ds", [])
            level_list = song.get("level", [])

            for idx, ds in enumerate(ds_list):
                level_str = level_list[idx] if idx < len(level_list) else str(ds)
                ach_str, actual_ra = self._calc_min_ach_for_ra(ds, target_ra)
                if ach_str is not None:
                    matched_charts.append({
                        "name": song_name,
                        "level_str": level_str,
                        "ds": ds,
                        "ach": ach_str,
                        "ra": actual_ra
                    })

        if not matched_charts:
            yield event.plain_result(f"未找到可达到单曲 Rating >= {target_ra} 的曲目。")
            return
        #排序模块| limit 限制输出 | selceted列表
        matched_charts.sort(key=lambda x: (x["ds"], x["name"]))
        display_limit = 20
        selected = matched_charts[:display_limit]

        lines = [f"🎯 达到单曲 Rating ≥ {target_ra} 推荐曲目（共找到 {len(matched_charts)} 个谱面，按等级从小到大）：\n"]
        for item in selected:
            lines.append(f'"{item["name"]}" {item["level_str"]} {item["ach"]}')

        if len(matched_charts) > display_limit:
            lines.append(f"\n... 篇幅原因仅展示前 {display_limit} 首曲目。")

        yield event.plain_result("\n".join(lines))