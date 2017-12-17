import pandas as pd
import datetime
import matplotlib.pyplot as plt
from weasyprint import HTML, CSS
from wand.image import Image as WImage
import os
import re

# Functions to relabel default clinics, encounters, and providers


def clinic_relabel(clinic):
    pattern = r'([a-zA-z]+)\s?([a-zA-z]+)?\s?([a-zA-z]+)?\s?(\[\d+\])'
    match = re.match(pattern, clinic)
    if match:
        clinic_name = match.group(1)[:3]
        if match.group(2) == "GRSH":
            clinic_name += ' G'
        if match.group(3) == 'TEL':
            clinic_name += ' T'
        return clinic_name
    else:
        return f"Invalid Clinic '{clinic}'"


def encounter_relabel(encounter, category=None):
    labels = {
        'New Pt': ['AC NEW PAT', 'AC NEW', 'AC NEW PT', 'AC NP', 'NP'],
        'Return': ['AC RET PT', 'AC RETURN', 'AC RETURN PT', 'AC RTRN PT', 'OVR'],
        'PST': ['OMW PST', 'AC PST', 'PST', 'OSV PST'],
        'PST Teach': ['PST TEACH', 'AC PST TEACH', 'AC PST Teach', 'AC PST TEACH'],
        'Ext': ['AC EXTEND', 'AC EXTENDED', 'AC EXT', 'OSV AC EX', 'OVE'],
        'Tele': ['AC PHONE', 'ONB TELEPHON', 'AC PHONE', 'AC PHONE', 'OMW AC TELE', 'ONB AC TELE', 'OPH AC TELE', 'OSV AC TELE', 'tele visit'],
        'MS NP': ['NP MS', 'NP MS'],
        'MS Rt': ['MS RETURN'],
        'MS Tel': ['MS TELE', 'MS TELE'],
        'DOAC': ['OMW AC DOAC', 'ONB AC DOAC', 'ONB AC DOAC', 'OPH AC DOAC', 'OPH AC DOAC', 'OSV AC DOAC'],
        'NP Hep': ['NP HEP', 'NP HEP 30'],
        'HP Tel': ['HEP TELE']
        }
    pattern = r'(.+)(\s\[\d+\])'
    match = re.match(pattern, encounter)
    if match:
        encounter_stripped = match.group(1).strip()
        found = False
        for abv in labels:
            if encounter_stripped in labels[abv]:
                found = True
                return abv
        if not found:
            if category:
                if encounter not in category:
                    category.append(encounter)
            return encounter
    else:
        return f"Invalid Encounter '{encounter}'"


def provider_relabel(provider):
    pattern = r"([a-zA-Z'-]+),\s([a-zA-z'-]+)\s?([a-zA-Z'-]+)?$"
    match = re.match(pattern, provider)
    if match:
        lastname = match.group(1)
        firstname = match.group(2)
        middlename = match.group(3)
        if middlename:
            initials = firstname[0] + middlename[0] + lastname[0]
            return initials.upper()
        else:
            initials = firstname[0] + lastname[0]
            return initials.upper()
    else:
        return f"Invalid Provider '{provider}'"

# Raw data manipulation


def data_adj(filename):
    # month_cat =['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    encounter_cat = ['Return', 'Tele', 'PST', 'New Pt', 'Ext', 'DOAC', 'PST Teach', 'MS NP', 'MS Rt', 'MS Tel', 'NP Hep', 'HP Tel']
    data = pd.read_csv(filename, usecols=['Date', 'Dept/Loc', 'Type', 'Prov/Res'])
    data.columns = ['date', 'clinic', 'encounter', 'prov']
    data.date = pd.to_datetime(data.date)
    data.clinic = data.clinic.apply(clinic_relabel)
    # data.encounter = data.encounter.apply(encounter_relabel, args=(encounter_cat,))
    data.encounter = data.encounter.apply(lambda x: encounter_relabel(x, encounter_cat))
    data.encounter = data.encounter.astype('category', ordered=True, categories=encounter_cat)
    data['day'] = data.date.apply(lambda x: datetime.datetime.strftime(x, '%-m/%d'))
    data['prov_initials'] = data.prov.apply(provider_relabel)
    return data

# Tables setup


def encounter_period(data, clinic='All'):
    if clinic != "All":
        data = data[data.clinic.str.contains(clinic)]
    pivot = data.pivot_table(index='prov', columns='encounter', values='date', aggfunc=len, fill_value=0, margins=True, margins_name='Total')
    pivot = pivot.loc[:, (pivot != 0).any(axis=0)]
    pivot.sort_values('Total', ascending=False, inplace=True)
    pivot.drop(['Total'], inplace=True)
    pivot.loc['Total'] = pivot.sum()
    return pivot.rename_axis(None)


def encounter_day(data, clinic='All'):
    if clinic != "All":
        data = data[data.clinic.str.contains(clinic)]
    pivot = data.pivot_table(index='encounter', columns='day', values='date', aggfunc=len, fill_value=0, margins=True, margins_name='Total')
    pivot = pivot[pivot['Total'] > 0]
    pivot['Total'] = pivot['Total'].astype(int)
    pivot.loc["#Pharm"] = pivot.apply(lambda x: len(data[data.day == x.name].prov.unique()))
    return pivot.rename_axis(None)


def provider_day(data, clinic='All'):
    encounter_cat = ['Return', 'Tele', 'PST', 'New Pt', 'Ext', 'DOAC', 'PST Teach', 'MS NP', 'MS Rt', 'MS Tel', 'NP Hep', 'HP Tel']
    if clinic != "All":
        data = data[data.clinic.str.contains(clinic)]
    pivot = data.pivot_table(index=['encounter', 'prov'], columns='day', values='date', aggfunc=len, fill_value=0, margins=True, margins_name='Total')
    pivot = pivot[pivot.loc[:]['Total'] > 0]
    pivot = pivot.sort_values(by=['Total'], ascending=False).swaplevel(0, 1).sort_index(level=1, sort_remaining=False).swaplevel(0, 1)
    pivot['Total'] = pivot['Total'].astype(int)
    pivot = pivot.reindex(encounter_cat, level=0)
    return pivot.rename_axis([None, None])


def provider_worked_days(data, clinic='All'):
    if clinic != "All":
        data = data[data.clinic.str.contains(clinic)]
    pivot = data.pivot_table(index='prov_initials', columns='clinic', values='date', aggfunc=lambda x: len(x.unique()), fill_value=0)
    pivot.sort_values(by=pivot.iloc[:, 0].name, ascending=False, inplace=True)
    return pivot.rename_axis(None)


def provadj_days(data, clinic='All'):
    def num_eq(value):
        split = value.split('(')
        split[1] = split[1][:-1]
        if split[0] == split[1]:
            return split[0]
        else:
            return value

    def adj_total(value):
        if value.find('(') != -1:
            split = value.split('(')
            total = split[1][:-1]
            return int(total)
        else:
            return int(value)
    if clinic != "All":
        data = data[data.clinic.str.contains(clinic)]
    pivot = data.pivot_table(index=['prov', 'encounter'], columns='day', values='date', aggfunc=len, fill_value=0, margins=True, margins_name='Total')
    pivot = pivot[pivot.loc[:]['Total'] > 0]
    pivot['Total'] = pivot['Total'].astype(int)

    providers = pivot.index.levels[0]
    adj = {'New Pt': 3, 'Ext': 2}

    prov_series = []

    for provider in providers:
        adj_pivot = pivot.loc[provider]
        adj_pivot.loc['Total'] = adj_pivot.sum()
        adj_enc = []
        total_dif = 0
        for encounter in adj:
            if encounter in adj_pivot.index:
                adj_enc.append(adj_pivot.loc[encounter].apply(lambda x: x * adj[encounter]) - adj_pivot.loc[encounter])
        for encounter in adj_enc:
            total_dif += encounter
        total_dif += adj_pivot.loc['Total']
        adj_pivot.loc['Total'] = adj_pivot.loc['Total'].astype(str) + '(' + total_dif.astype(str) + ')'
        adj_pivot.loc['Total'] = adj_pivot.loc['Total'].apply(num_eq)
        prov_series.append(adj_pivot.loc['Total'].rename(provider))

    adj_table = pd.concat(prov_series, axis=1).transpose()
    adj_table['adj_total'] = adj_table['Total'].apply(adj_total)
    adj_table.sort_values('adj_total', ascending=False, inplace=True)
    adj_table.drop(['adj_total'], axis=1, inplace=True)
    adj_table.drop(['Total'], inplace=True)
    return adj_table
