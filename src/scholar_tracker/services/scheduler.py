from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..config import settings
from ..models.database import get_total_citations, get_tracked_papers, update_paper_citations
from ..utils.logger import logger
from .notifier import notifier
from .scraper import _backoff_sleep, scraper_client


async def check_citations():
    logger.info("Starting scheduled citation check...")

    papers = get_tracked_papers()
    if not papers:
        if settings.scholar_author_id:
            logger.info("First run: loading author profile...")
            try:
                author = scraper_client.fetch_author(settings.scholar_author_id)
                for pub in author.get('publications', []):
                    title = pub.get('bib', {}).get('title')
                    cites = pub.get('num_citations', 0)
                    if title:
                        update_paper_citations(title, cites)
                papers = get_tracked_papers()
            except Exception as e:
                logger.error(f"Failed to seed author profile: {e}")
                return
        else:
            logger.warning("No tracked papers and SCHOLAR_AUTHOR_ID not set.")
            return

    new_citations = []
    failed_papers = []

    for i, paper in enumerate(papers):
        title = paper['title']
        try:
            if i > 0:
                _backoff_sleep()

            pub = scraper_client.find_paper_by_title(title)
            if not pub:
                logger.warning(f"Paper not found on Scholar: '{title}'")
                continue

            current = pub.get('num_citations', 0)

            has_changed, delta = update_paper_citations(title, current)
            if has_changed and delta > 0:
                new_citations.append(f"{title}: +{delta} (total: {current})")

        except Exception as e:
            logger.error(f"Failed to check paper '{title}': {e}")
            failed_papers.append(title)
            continue

    checked = len(papers) - len(failed_papers)
    logger.info(
        f"Citation check complete: {checked}/{len(papers)} papers checked, "
        f"{len(new_citations)} with new citations, {len(failed_papers)} failures"
    )

    if new_citations:
        total = get_total_citations()
        message_body = "New Citations Detected!\n" + "-" * 20 + "\n"
        message_body += "\n".join(new_citations)
        message_body += "\n" + "-" * 20 + f"\nTotal: {total}"

        for num in settings.whitelisted_numbers:
            try:
                logger.info(f"Sending new citation notification to {num}")
                await notifier.send_template(num, component_params=[
                    {"type": "text", "text": str(len(new_citations))},
                    {"type": "text", "text": str(
                        sum([int(c.split('+')[1].split(' ')[0]) for c in new_citations]))},
                    {"type": "text", "text": str(total)}
                ])
                await notifier.send_text(num, message_body)
            except Exception as e:
                logger.error(f"Failed to send notification to {num}: {e}")

scheduler = AsyncIOScheduler()
scheduler.add_job(check_citations, "interval", hours=settings.check_interval_hours)
