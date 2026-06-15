import streamlit as st


def normalize_ticker(ticker):

    if ticker is None:
        return ""

    return str(ticker).strip().upper()


def add_ticker(sector, ticker):

    ticker = normalize_ticker(ticker)

    if not ticker:
        return

    basket = st.session_state.sectors[sector]["basket"]

    if ticker not in basket:
        basket.append(ticker)


def remove_ticker(sector, ticker):

    ticker = normalize_ticker(ticker)

    basket = st.session_state.sectors[sector]["basket"]

    if ticker in basket:
        basket.remove(ticker)


def mutate_and_rerun(fn, sector, ticker):

    fn(sector, ticker)

    st.session_state.force_rebuild = True

    st.rerun()