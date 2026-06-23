
from helpers.render_sector import render_sector_dashboard 
from helpers.render_ai_macro import render_ai_macro_dashboard 

                            
def render_all_dashboards(
    tabs,
    sector,
    sector_data,
    sector_metrics,
    fred_data,
    market_sentiment
):

    with tabs[0]:

        render_ai_macro_dashboard(
            sector_metrics,
            sector_data,
            fred_data,
            #edgar_data,
            market_sentiment
        )
        
    for i, sector in enumerate(sector_data.keys()):

        if sector not in sector_data or sector not in sector_metrics:
            print("SKIPPING MISSING SECTOR:", sector)
            continue
        
        with tabs[i + 1]:

            render_sector_dashboard(
                sector,
                sector_data[sector],
                sector_metrics[sector]
            )
             
