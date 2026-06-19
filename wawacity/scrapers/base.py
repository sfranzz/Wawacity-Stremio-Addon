from typing import List, Dict, Optional, Any
from selectolax.parser import HTMLParser, Node
from re import escape, match, search
from wawacity.utils.http_client import http_client

class BaseScraper:
    
    # --- Link extraction ---
    @staticmethod
    def extract_link_from_node(node: Node) -> Optional[str]:
        link = None
        attributes = node.attributes
        
        if "href" in attributes:
            link = attributes["href"]
        else:
            for value in attributes.values():
                if search(r"^(/|https?:)\w", value):
                    link = value
                    break
        return link
    
    # --- Node filtering ---
    @staticmethod
    def filter_nodes(nodes: List[Node], pattern: str) -> List[Node]:
        filtered = []
        for node in nodes:
            if isinstance(node, Node) and search(pattern, node.text()):
                filtered.append(node)
        return filtered
    
    # --- Quality sorting ---
    @staticmethod
    def quality_sort_key(item: Dict[str, Any]) -> tuple:
        q = str(item.get("quality", "")).upper()
        
        # --- 4K detection ---
        is_4k = "2160" in q or "4K" in q or "UHD" in q
        
        # --- 1080p detection ---
        is_1080 = "1080" in q or q == "HD"
        
        # --- 720p detection ---
        is_720 = "720" in q
        
        # --- Release type ranking ---
        if "REMUX" in q:
            release_type = 0
        elif "BLURAY" in q or "BLU-RAY" in q:
            release_type = 1
        elif "WEB-DL" in q or "WEBDL" in q:
            release_type = 2
        elif "HDLIGHT" in q or "LIGHT" in q:
            release_type = 3
        elif "WEBRIP" in q:
            release_type = 4
        elif "HDRIP" in q:
            release_type = 5
        else:
            release_type = 99
        
        # --- Final sorting priority ---
        if is_4k:
            return (0, release_type)
        elif is_1080:
            return (1, release_type)
        elif is_720:
            return (2, release_type)
        else:
            return (99, release_type)

    # --- Generic search logic ---
    async def _search_generic(
        self,
        title: str,
        year: Optional[str],
        base_url: str,
        search_path: str,
        link_prefix: str,
        label: str,
        title_selector: str = "div.wa-sub-block-title:has(i.flag)",
        separator: str = "|",
    ) -> Optional[Dict]:
        from wawacity.utils.helpers import quote_url_param
        from wawacity.utils.logger import logger

        encoded_title = quote_url_param(str(title)[:31])
        search_url = f"{base_url}/?p={search_path}&search={encoded_title}"
        if year:
            search_url += f"&year={str(year)}"

        logger.log("SCRAPER", f"Searching {label}: {search_url}")

        try:
            # Step 1: Find media link
            response = await http_client.get(search_url)
            if response.status_code != 200:
                logger.error(f"Search failed for {label}: {response.status_code}")
                return None

            search_link_selector = f'div.wa-sub-block-title a[href^="{link_prefix}"]'
            parser = HTMLParser(response.text)
            search_nodes = parser.css(search_link_selector)

            target_title = title.lower().strip()
            if not search_nodes:
                # Fallback to search by letter
                if not target_title:
                    return None
                first_letter = target_title[0]
                search_url = f"{base_url}/?p={search_path}{f'&year={str(year)}' if year else ''}&letter={first_letter}"
                response = await http_client.get(search_url)
                if response.status_code != 200:
                    logger.error(f"Search failed for {label}: {response.status_code}")
                    return None
                parser = HTMLParser(response.text)
                search_nodes = parser.css(search_link_selector)
                if not search_nodes:
                    logger.error(f"No {label} links found for '{title}'")
                    return None
            
            best_match_link = None
            best_match_score = 0  # 0: no match, 1: 'in', 2: 'startswith', 3: 'exact'
            # ^ : start with title
            # (?: - saison \d+)? : optional for title - (Saison X) pattern
            # (?: \([^)]+\))? : optional for eventual (LANGUAGE) pattern at the end
            # $ : end of line
            exact_series_pattern = rf"^{escape(target_title)}(?: - saison \d+)?(?: \([^)]+\))?$"

            for node in search_nodes:
                node_text = node.text(strip=True).lower()
                current_link = node.attributes.get("href", "")

                # Exact match
                if (node_text == target_title) or bool(match(exact_series_pattern, node_text)):
                    best_match_link = current_link
                    best_match_score = 3
                    break

                # 2. Start with (medium-high score)
                elif node_text.startswith(target_title):
                    if best_match_score < 2:
                        best_match_link = current_link
                        best_match_score = 2

                # 3. Contains (lowest score)
                elif target_title in node_text:
                    if best_match_score < 1:
                        best_match_link = current_link
                        best_match_score = 1

            # fallback
            if not best_match_link:
                logger.warn(f"No exact match found for '{title}', falling back to first result.")
                best_match_link = search_nodes[0].attributes.get("href", "")

            first_link = best_match_link

            # Step 2: Get title from content page
            detail_url = f"{base_url}/{first_link}"
            response2 = await http_client.get(detail_url)
            if response2.status_code != 200:
                return {"link": first_link, "text": f"{title} [{year}]" if year else title}

            parser2 = HTMLParser(response2.text)
            title_nodes = parser2.css(title_selector)

            if title_nodes:
                page_title = title_nodes[0].text(strip=True, separator=separator)
                if not page_title.strip():
                    return {"link": first_link, "text": f"{title} [{year}]" if year else title}
                return {"link": first_link, "text": page_title}

            return {"link": first_link, "text": f"{title} [{year}]" if year else title}

        except Exception as e:
            logger.error(f"Failed to search {label}: {e}")
            return None