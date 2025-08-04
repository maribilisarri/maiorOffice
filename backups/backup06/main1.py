import ast
import shutil
import pandas as pd
import os
import random
from datetime import datetime, timedelta
import re
import glob
import logging
from collections import defaultdict

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
#-----------------Paths------------------------
input_dir='input'
static_dir = 'static'
timetable_dir='timetable-output'
blocks_dir="blocks-output"
duties_dir="duties-output"
history_dir='history'
#combined_output_path = 'output/combined_all_timetables.csv'
for d in (timetable_dir,blocks_dir,duties_dir,history_dir):
    os.makedirs(d, exist_ok=True)







# ----------- Λειτουργία: 'test' ή 'final' -------------

while True:
    MODE = input("Επιλέξτε mode ('test' ή 'final'): ").strip().lower()
    if MODE in ('test', 'final'):
        break
    print("❌ Μη έγκυρη επιλογή.  'test' ή 'final'")
final = (MODE == 'final')


# ----------- Ιστορικό IDs (μόνο σε final mode) -------------
trip_history_file = os.path.join(history_dir, 'used_trip_ids.txt')
duty_history_file = os.path.join(history_dir, 'used_duty_ids.txt')
used_trip_ids = set()
used_duty_ids = set()

if MODE == 'final':
    if os.path.exists(trip_history_file):
        with open(trip_history_file, 'r') as f:
            for line in f:
                uid = line.strip()
                if uid:
                    used_trip_ids.add(uid)

    if os.path.exists(duty_history_file):
        with open(duty_history_file, 'r') as f:
            for line in f:
                uid = line.strip()
                if uid:
                    used_duty_ids.add(uid)

# ----------- Random seed σε test mode -------------
if MODE == 'test':
    random.seed(12345)
    #--------------------------- ----------- Βοηθητικές Συναρτήσεις -------------------------------------
# ----------- Συνάρτηση για ασφαλές random ID -------------
def get_unique_9digit(used_ids_set):
    while True:
        new_id = str(random.randint(10**8, 10**9 - 1))
        if MODE == 'test' or new_id not in used_ids_set:
            if MODE == 'final':
                used_ids_set.add(new_id)
            return new_id

# ----------- Συνάρτηση για αποθήκευση ιστορικού -------------
def save_history():
    if MODE != 'final':
        return
    with open(trip_history_file, 'w') as f:
        for tid in sorted(used_trip_ids):
            f.write(f"{tid}\n")
    with open(duty_history_file, 'w') as f:
        for did in sorted(used_duty_ids):
            f.write(f"{did}\n")



# Αν η τιμή της VEHBLOCK_ID περιέχει οποιοδήποτε γράμμα, θέτουμε '99'

def replace_if_contains_letter(value):
    if pd.isna(value):
        return value
    return re.sub(r'\D+', '99', str(value))


#==================================================================================TIME==================================================
#===========================================================================================================================================
def parse_extended_time(time_str):
    """
    Παίρνει string "HH:MM:SS" όπου HH μπορεί να είναι <24 ή >=24.
    Επιστρέφει ένα datetime αντικείμενο:
      - Αν HH >= 24, τοποθετεί το αποτέλεσμα σε επόμενη ημέρα (1900-01-02)
      - Αν HH <  24, στην ίδια ημέρα (1900-01-01)
    Αν το time_str δεν μπορεί να γίνει parse, επιστρέφει pd.NaT.
    """
    try:
        s = str(time_str).strip()
        if ' ' in s:
            s = s.split(' ')[-1]  # Κρατάει μόνο την ώρα
        if len(s.split(':')) == 2:
            s += ':00'

        h, m, s = map(int, s.split(':'))
        if h >= 24:
            # π.χ. "24:05:00" → 1900-01-02 00:05:00
            return datetime(1900, 1, 2, h - 24, m, s)
        else:
            # π.χ. "23:50:00" → 1900-01-01 23:50:00
            return datetime(1900, 1, 1, h, m, s)
    except:
        return pd.NaT

def average_time(t1, t2):
    """
    Υπολογίζει τον μέσο χρόνο ανάμεσα σε δύο "extended" time-strings.
    Παράδειγμα:
      t1 = "23:40:00", t2 = "00:10:00"  → αποτέλεσμα "24:25:00"
      t1 = "24:01:00", t2 = "00:25:00"  → αποτέλεσμα "24:13:00"
    Διαδικασία:
      1) parse και των δύο σε datetime με parse_extended_time
      2) αν dt2 < dt1, θεωρούμε ότι το t2 ανήκει στην επόμενη ημέρα → dt2 += 1 day
      3) mid = dt1 + (dt2 - dt1) / 2
      4) αν mid.day == 2, τότε επιστρέφουμε hour + 24, αλλιώς hour κανονικά
    Επιστρέφει string "HH:MM:SS" όπου HH >= 24 εάν χρειάζεται.
    """
    dt1 = parse_extended_time(t1)
    dt2 = parse_extended_time(t2)
    if pd.isna(dt1) or pd.isna(dt2):
        # fallback αν δεν parse-αρει
        return t1

    # Αν η δεύτερη ώρα φαίνεται μικρότερη, προσθέτουμε 1 ημέρα
    if dt2 < dt1:
        dt2 += timedelta(days=1)
    mid = dt1 + (dt2 - dt1) / 2
    if mid.day == 2:
        h = mid.hour + 24
    else:
        h = mid.hour
    return f"{h:02}:{mid.minute:02}:00"

def fix_excel_datetime_to_extended_hour_format(value, threshold_hour=4):
    """
    Παίρνει value που μπορεί να είναι:
      - pd.Timestamp ή datetime
      - float/int (Excel time fraction, π.χ. 0.5 → 12:00:00)
      - string:
         * "HH:MM" ή "HH:MM:SS"
         * "1900-01-01 HH:MM:SS" ή "1/1/1900 HH:MM:SS"
    Επιστρέφει string "HH:MM:SS" όπου, αν hour < threshold_hour (π.χ. 4),
    προσθέτει +24 (extended format). Αν δεν μπορεί να γίνει parse επιστρέφει 'NaT'.
    """
    try:
        # 1) Αν είναι Timestamp / datetime
        if isinstance(value, (pd.Timestamp, datetime)):
            hour   = value.hour
            minute = value.minute
            second = value.second

        # 2) Αν είναι float/int (Excel time fraction)
        elif isinstance(value, (float, int)):
            total_seconds = int(value * 24 * 3600)
            hour   = total_seconds // 3600
            minute = (total_seconds % 3600) // 60
            second = total_seconds % 60

        else:
            # 3) Αν είναι string
            s = str(value).strip()

            # 3α) Αν περιέχει "1900-01-01" ή "1/1/1900", κρατάμε μόνο το κομμάτι της ώρας
            #if '1900-01-01' in s or '1/1/1900' in s or '1900-01-02' in s or '1900-01-03' in s or '1900-11-01' in s:

            if ' ' in s:
                s = s.split(' ')[-1]  # το κομμάτι της ώρας
            if len(s.split(':')) == 2:
                s += ':00'
                t = datetime.strptime(s, "%H:%M:%S")
                hour   = t.hour
                minute = t.minute
                second = t.second
            else:
                # 3β) Αν δεν έχει prefix, υποθέτουμε "HH:MM" ή "HH:MM:SS"
                parts = s.split(':')
                if len(parts) == 2:
                    # π.χ. "0:00" → "00:00:00"
                    s = f"{int(parts[0]):02}:{int(parts[1]):02}:00"
                t = datetime.strptime(s, "%H:%M:%S")
                hour   = t.hour
                minute = t.minute
                second = t.second

        # 4) Αν hour < threshold_hour (π.χ. 4), θεωρούμε μετά μεσάνυχτα → hour += 24
        if hour < threshold_hour:
            hour += 24

        return f"{hour:02}:{minute:02}:{second:02}"

    except:
        return 'NaT'

def adjust_overlapping_times(df):
    """
    Για κάθε VB_COMPANYCODE ελέγχει αν το ΤΕΡΜΑ της τρέχουσας
    εγγραφής είναι > ΑΝΑΧΩΡΗΣΗ της επόμενης. Αν ναι, μικραίνει
    τον τερματισμό ώστε να είναι 1 λεπτό πριν την επόμενη αναχώρηση,
    διατηρώντας το “extended format” της ώρας (π.χ. “24:01:00”).
    """


    changes = 0
    try:
        #for (vb_code, direction), group in df.groupby(['VB_COMPANYCODE', 'DIRECTION']):
        for (vb_code), group in df.groupby(['VB_COMPANYCODE']):
            group = group.copy()
            # Στήλη για ταξινόμηση
            group['ΑΝΑΧΩΡΗΣΗ_dt'] = group['ΑΝΑΧΩΡΗΣΗ'].apply(parse_extended_time)
            group = group.sort_values(by='ΑΝΑΧΩΡΗΣΗ_dt').drop(columns='ΑΝΑΧΩΡΗΣΗ_dt')

            for i in range(len(group) - 1):
                idx_now  = group.index[i]
                idx_next = group.index[i + 1]

                t_end        = parse_extended_time(df.at[idx_now,  'ΤΕΡΜΑ'])
                t_next_start = parse_extended_time(df.at[idx_next, 'ΑΝΑΧΩΡΗΣΗ'])

                if pd.notna(t_end) and pd.notna(t_next_start) and t_end > t_next_start:
                    # Μειώνουμε το τρέχον “ΤΕΡΜΑ” κατά 1 λεπτό,
                    # διατηρώντας το extended format:
                    #new_dt   = t_next_start - timedelta(minutes=1)
                    new_time = (t_next_start - timedelta(minutes=1)).strftime('%H:%M:%S')
                    df.at[idx_now, 'ΤΕΡΜΑ'] = new_time
                    changes += 1

            last_idx = group.index[-1]
#DEBUG#
            #print("✔ Τελευταία εγγραφή για", vb_code, ":",
           #       df.loc[last_idx, ['ΑΝΑΧΩΡΗΣΗ', 'ΤΕΡΜΑ']])

        print(f"🔧 Έγιναν {changes} αλλαγές overlapping στις ώρες ΤΕΡΜΑ ανά VB_COMPANYCODE")
    except Exception as e:
        print(f"Σφάλμα στη ρύθμιση overlapping: {e}")
    return df

#==================================================================================TIME==================================================
#===========================================================================================================================================

def assign_duty_ids(df):
    """
    Παίρνει DataFrame που περιέχει στήλη 'DUTY_COMPANYCODE' κ.ά.
    Δημιουργεί τυχαίο DUTY_ID για κάθε μοναδικό DUTY_COMPANYCODE που έχει '_',
    επιστρέφοντας νέο DataFrame με επιπλέον στήλη 'DUTY_ID' και ταξινομημένο.
    """
    df = df.copy()
    unique_duties = df['DUTY_COMPANYCODE'].dropna().unique()
    duty_map = {

        duty: get_unique_9digit(used_duty_ids)
        for duty in unique_duties if '_' in duty
    }
    df['DUTY_ID'] = df['DUTY_COMPANYCODE'].map(duty_map)
    df.sort_values(['DUTY_COMPANYCODE', 'START_TIME'], inplace=True)
    return df
def make_short_duty(df):
    """
    Παίρνει το “done” DataFrame (που έχει ήδη στήλη 'DUTY_ID'),
    δημιουργεί πεδίο “ShortDuty” – μία γραμμή ανά DUTY_COMPANYCODE
    με ελάχιστο START_TIME & μέγιστο END_TIME.
    Επιστρέφει το summary DataFrame στις ίδιες στήλες.
    """
    print(f"➡️ Δημιουργία ShortDuty από: ")
    original_columns = df.columns.tolist()

    grouped = df.groupby('DUTY_COMPANYCODE')
    summary_rows = []

    for duty, group in grouped:
        # Ταξινόμηση με βάση το START_TIME (ως string)
        group_sorted_by_start = group.sort_values(by='START_TIME', ascending=True, na_position='last')
        first_row = group_sorted_by_start.iloc[0]
        first_start_node = first_row['STARTNODE_COMPANYCODE']
        first_start_time = first_row['START_TIME']
        first_start_basin = first_row.get('STARTNODE_BASIN', '')
        first_start_comp = first_row.get('STARTNODE_COMPANY', '')

        # Ταξινόμηση με βάση το END_TIME (ως string)
        group_sorted_by_end = group.sort_values(by='END_TIME', ascending=True, na_position='last')
        last_row = group_sorted_by_end.iloc[-1]
        last_end_node = last_row['ENDNODE_COMPANYCODE']
        last_end_time = last_row['END_TIME']
        last_end_basin = last_row.get('ENDNODE_BASIN', '')
        last_end_comp = last_row.get('ENDNODE_COMPANY', '')

        # Δημιουργία συνοπτικής γραμμής
        summary = first_row.copy()

        summary['STARTNODE_COMPANYCODE'] = first_start_node
        summary['STARTNODE_BASIN'] = first_start_basin
        summary['STARTNODE_COMPANY'] = first_start_comp
        summary['START_TIME'] = first_start_time

        summary['ENDNODE_COMPANYCODE'] = last_end_node
        summary['ENDNODE_BASIN'] = last_end_basin
        summary['ENDNODE_COMPANY'] = last_end_comp
        summary['END_TIME'] = last_end_time

        summary_rows.append(summary)

        # Δημιουργία DataFrame
    short_df = pd.DataFrame(summary_rows)

    # στήλες στην ίδια σειρά
    short_df = short_df[original_columns]
    return short_df


# ====================================TIMETABLE=================================
##διαγραφω αν υπαρχει τον φακελο timetable-output
def clean_timetable_dir():
    if os.path.exists(timetable_dir):
        shutil.rmtree(timetable_dir)
    os.makedirs(timetable_dir,exist_ok=True)




def timetable_and_combine():
    print("▶ Δημιουργία Timetable...")
#def timetable(input_dir,filename,sheet_name):
    # ----------- Στατικά δεδομένα -------------
    patterns_df = pd.read_csv(os.path.join(static_dir, 'Pattern.csv'), sep=';', dtype=str)
    length_df = pd.read_csv(os.path.join(static_dir, 'PatternAttributes.csv'), sep=';', dtype=str)
    patterns_df.rename(columns={'PATTERNCODE': 'PATTERN'}, inplace=True)
    patterns_df['PATTERN'] = patterns_df['PATTERN'].str.strip()
    patterns_df['DIRECTION'] = patterns_df['DIRECTION'].str.strip()
    length_df['PATTERNCODE'] = length_df['PATTERNCODE'].str.strip()
    length_df['CONVLENGTH'] = length_df['CONVLENGTH'].str.strip()
    operating_days_df = pd.read_csv(os.path.join(static_dir, 'Operating_Days.csv'), sep=';', dtype=str)
    valid_operating_days = set(operating_days_df['Operating_Days'].dropna().str.strip())
    invalid_log_lines = []
    # ----------- Επεξεργασία κάθε input αρχείου -------------
    for filename in os.listdir(input_dir):
        if not filename.endswith('.xlsx'):
            continue

        input_path = os.path.join(input_dir, filename)
        base_name = os.path.splitext(filename)[0]
        xls = pd.ExcelFile(input_path)



        for sheet_name in xls.sheet_names:
            print(f" Επεξεργασία αρχείου: {filename} | Φύλλο: {sheet_name}")
            print("📌 Στήλες στο Pattern.csv:", patterns_df.columns.tolist())

            # Διαβάζουμε ως string ώστε να πιάσουμε μορφές "0:00", "23:50", "1/1/1900 00:03" κ.λπ.
            input_df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str)
            # LOG
            # Μέτρηση "1900-01-01" για έλεγχο
            count_ana = input_df['ΑΝΑΧΩΡΗΣΗ'].astype(str).str.contains('1900-01-01', na=False).sum()
            count_term = input_df['ΤΕΡΜΑ'].astype(str).str.contains('1900-01-01', na=False).sum()
#DEEBUG#
            #print(f" Ανιχνεύθηκαν {count_ana} φορές '1900-01-01' στην ΑΝΑΧΩΡΗΣΗ")
            #print(f" Ανιχνεύθηκαν {count_term} φορές '1900-01-01' στο ΤΕΡΜΑ")
            count_ana1 = input_df['ΑΝΑΧΩΡΗΣΗ'].astype(str).str.contains('1900-01-02', na=False).sum()
            count_term1 = input_df['ΤΕΡΜΑ'].astype(str).str.contains('1900-01-02', na=False).sum()
            #print(f" Ανιχνεύθηκαν {count_ana1} φορές '1900-01-02' στην ΑΝΑΧΩΡΗΣΗ")
            #print(f" Ανιχνεύθηκαν {count_term1} φορές '1900-01-02' στο ΤΕΡΜΑ")

            #  Εφαρμογή του helper σε όλες τις τιμές
            input_df['ΑΝΑΧΩΡΗΣΗ'] = input_df['ΑΝΑΧΩΡΗΣΗ'].apply(fix_excel_datetime_to_extended_hour_format)
            input_df['ΤΕΡΜΑ'] = input_df['ΤΕΡΜΑ'].apply(fix_excel_datetime_to_extended_hour_format)

            #  Διορθώσεις overlapping
            input_df = adjust_overlapping_times(input_df)

            input_df['PATTERN'] = input_df['PATTERN'].str.strip()
            input_df['MERGE_KEY'] = input_df.index
            input_df['LINE_EXCEL'] = input_df['LINE']
            input_df['EXCEL_NAME'] = filename
            #print (input_df)


    # LINE_EXCEL
            #output_df = output_df.merge(input_df[['MERGE_KEY', 'LINE_EXCEL']], on='MERGE_KEY', how='left')
# DEEBUG#
            # print(input_df[['ΑΝΑΧΩΡΗΣΗ','ΤΕΡΜΑ']].head())
            # print("📌 Στήλες στο Pattern.csv:", patterns_df.columns.tolist())

            #  Merge με patterns_df
            #  Δημιουργία unique map PATTERN → DIRECTION
            # αφαιρώ direction  απο input  για να μην μεινει η παλια στηλη
            input_df = input_df.drop(columns=['DIRECTION'], errors='ignore')
            input_df["LINE"]=None
            #input_df = input_df.drop(columns=['LINE'], errors='ignore')
            #input_df = input_df.rename(columns={'LINE': 'LINE'}, inplace=True)
            # input_df = input_df.join(pattern_dir_map, on='PATTERN')
            merged = input_df.merge(
                patterns_df[['PATTERN', 'NODE', 'DIRECTION','LINE']],
                on='PATTERN', how='left'
            ).dropna(subset=['NODE'])
# DEEBUG#
            #print(merged[['PATTERN', 'NODE']].drop_duplicates().head(10))

            #  Merge με length_df
            merged = merged.merge(
                length_df[['PATTERNCODE', 'CONVLENGTH']].rename(columns={
                    'PATTERNCODE': 'PATTERN',
                    'CONVLENGTH': 'LENGTH'
                }),
                on='PATTERN', how='left'
            )

            #print(merged.head())
            merged.drop(columns=['LINE_x'], errors='ignore')
            merged.rename(columns={'LINE_y': 'LINE'}, inplace=True)

            #print(merged.head())
            #  Περιορισμός στις 3 πρώτες εγγραφές ανά δρομολόγιο
            try:
                merged = merged.groupby('MERGE_KEY').head(3)
            except Exception as e:
                print(e)
##DEEBUG#
            #print('merged arxika')
            #print(merged[['PATTERN', 'NODE', 'LENGTH']].head())
            #  Ορισμός τελικών στηλών
            target_columns = [
                'SERVICELEVEL', 'CALENDAR', 'OPERATINGDAY', 'PIECETYPE', 'STARTINGDATE',
                'ENDINGDATE', 'LINE', 'LINEBASIN', 'LINECOMPANY', 'PATTERN', 'DIRECTION',
                'TRIPCODE', 'TRIPCOMPANYCODE', 'ACTIVITYNUMBER', 'LENGTH', 'VEHBLOCKID',
                'DEPOT', 'VEHICLETYPE', 'VBLINE', 'VB_LINEBASIN', 'VB_LINECOMPANY',
                'PIECEORDER', 'ARRIVALTIME', 'DEPARTURETIME', 'NODE', 'NODEBASIN',
                'NODECOMPANY', 'PASSAGEORDER', 'BLOCK','LINE_EXCEL', 'EXCEL_NAME'
            ]
            output_df = pd.DataFrame(columns=target_columns)

            #  Mapping από merged -> output_df
            column_mapping = {
                'LINE': 'LINE',
                'LINE_EXCEL': 'LINE_EXCEL',
                'PATTERN': 'PATTERN',
                'DIRECTION': 'DIRECTION',
                'NODE': 'NODE',
                'LENGTH': 'LENGTH',
                'LINEBASIN': 'LINEBASIN',
                'OPERATINGDAY': 'OPERATINGDAY',
                'STARTINGDATE': 'STARTINGDATE',
                'ENDINGDATE': 'ENDINGDATE',
                'CALENDAR': 'CALENDAR',
                'MERGE_KEY': 'MERGE_KEY',
                'VB_COMPANYCODE': 'BLOCK',
                'EXCEL_NAME':'EXCEL_NAME'
            }

            for src, dst in column_mapping.items():
                if src in merged.columns:
                    output_df[dst] = merged[src]


            #output_df['LINE_EXCEL'] = input_df['LINE_EXCEL']

            #  Σταθερές στήλες
            output_df['SERVICELEVEL'] = 'F1'
            output_df['PIECETYPE'] = 'Revenue'
            output_df['LINECOMPANY'] = 'Def'
            output_df['NODEBASIN'] = 'OSETH'
            output_df['NODECOMPANY'] = 'Def'
            #  Μοναδικά IDs & PASSAGEORDER
            unique_ids_per_group = {

                key: get_unique_9digit(used_trip_ids)
                for key in output_df['MERGE_KEY'].unique()
            }
            output_df['TRIPCODE'] = output_df['MERGE_KEY'].map(unique_ids_per_group)
            output_df['TRIPCOMPANYCODE'] = output_df['TRIPCODE']
            output_df['ACTIVITYNUMBER'] = output_df['TRIPCODE']
            output_df['PASSAGEORDER'] = output_df.groupby('MERGE_KEY').cumcount() + 1

            ############isos to vgalo gia debugging

            #  assign_times με debug print για να εντοπίσω "00:02:00"
            def assign_times(group):
                try:
                    dep_time = input_df.loc[group['MERGE_KEY'].iloc[0], 'ΑΝΑΧΩΡΗΣΗ']
                    arr_time = input_df.loc[group['MERGE_KEY'].iloc[0], 'ΤΕΡΜΑ']
                    count = group.shape[0]
#DEBUGGING ORES
                    # Εκτυπώνουμε για debugging:
                    #print(f"DEBUG MERGE_KEY={group['MERGE_KEY'].iloc[0]}:")
                    #print(f"  dep_time (extended) = {dep_time}")
                    #print(f"  arr_time (extended) = {arr_time}")

                    for idx, row in group.iterrows():
                        po = row['PASSAGEORDER']
                        if po == 1:
                            group.at[idx, 'ARRIVALTIME'] = dep_time
                            group.at[idx, 'DEPARTURETIME'] = dep_time

                        elif po == 2 and count == 2:
                            group.at[idx, 'ARRIVALTIME'] = arr_time
                            group.at[idx, 'DEPARTURETIME'] = arr_time

                        elif po == 2 and count == 3:
                            mid = average_time(dep_time, arr_time)
#DEEBUG#
                           # print(f"  midpoint = average_time({dep_time}, {arr_time}) → {mid}")  # DEBUG
                            group.at[idx, 'ARRIVALTIME'] = mid
                            group.at[idx, 'DEPARTURETIME'] = mid

                        elif po == 3:
                            group.at[idx, 'ARRIVALTIME'] = arr_time
                            group.at[idx, 'DEPARTURETIME'] = arr_time

                except Exception as e:
                    print(f"Σφάλμα στην ώρα για MERGE_KEY={group['MERGE_KEY'].iloc[0]}: {e}")
                return group

            output_df = (
                output_df.groupby('MERGE_KEY', group_keys=False, sort=False).apply(assign_times).reset_index(drop=True)
                )

            #  Δημιουργία της στήλης DUTY
            def create_duty(row):
                duty_code = row['DUTY_COMPANYCODE']
                if pd.isna(duty_code):
                    return ''
                elif '_' in duty_code:
                    return duty_code
                else:
                    return f"{row['VB_COMPANYCODE']}_{duty_code}"

            duty_mapping = input_df[['MERGE_KEY', 'VB_COMPANYCODE', 'DUTY_COMPANYCODE']].copy()
            duty_mapping['DUTY'] = duty_mapping.apply(create_duty, axis=1)
            output_df = output_df.merge(
                duty_mapping[['MERGE_KEY', 'DUTY']], on='MERGE_KEY', how='left'
            )

            #  Μορφοποίηση ημερομηνιών
            output_df['STARTINGDATE'] = pd.to_datetime(
                output_df['STARTINGDATE'], errors='coerce'
            ).dt.strftime('%Y-%m-%d')
            output_df['ENDINGDATE'] = pd.to_datetime(
                output_df['ENDINGDATE'], errors='coerce'
            ).dt.strftime('%Y-%m-%d')



            output_df.drop(columns=['MERGE_KEY'], inplace=True)


            ############### Εξαγωγή Timetable CSV
            # Έλεγχος για μη έγκυρα OPERATINGDAY values
            invalid_days = set(output_df['OPERATINGDAY'].dropna().unique()) - valid_operating_days
            if invalid_days:
                message=print(f"⚠️ Μη έγκυρες τιμές OPERATINGDAY στο {base_name} - {sheet_name}: {sorted(invalid_days)}")
                #print(message)
                invalid_log_lines.append(message)

            safe_sheet = sheet_name.replace(" ", "_").replace("/", "-")


            #δημιουργια φακέλων για κάθε γραμμή και αποθήκευση των outputs
            line_folder = os.path.join(timetable_dir, base_name)
            os.makedirs(line_folder, exist_ok=True)
            output_path = os.path.join(line_folder, f"{base_name}_Timetable_{safe_sheet}.csv")
            output_df.to_csv(output_path, index=False, sep=';', encoding='utf-8')
            print(f"✅ Timetable αποθηκεύτηκε: {output_path}")

#LINEBASIN στο όνομα αρχείου
            # # Απόκτηση τιμής LINEBASIN (π.χ. 'Θεσσαλονίκη') και καθαρισμός
            # linebasin_values = output_df['LINEBASIN'].dropna().unique()
            # linebasin_str = str(linebasin_values[0]).replace(" ", "_") if len(linebasin_values) > 0 else "UnknownBasin"
            # # Δημιουργία φακέλου για κάθε γραμμή
            # line_folder = os.path.join(timetable_dir, base_name)
            # os.makedirs(line_folder, exist_ok=True)
            # # Ενσωμάτωση του LINEBASIN στο όνομα αρχείου
            # output_filename = f"{base_name}_{linebasin_str}_Timetable_{safe_sheet}.csv"
            # output_path = os.path.join(line_folder, output_filename)

            # δημιουργία φακέλου meres και αρχείων txt για κάθε sheet_name/μερα
            meres_folder = os.path.join(timetable_dir, 'meres')
            os.makedirs(meres_folder, exist_ok=True)
            meres_filename = f"{base_name}_meres.txt"
            meres_path = os.path.join(meres_folder, meres_filename)
            if not os.path.exists(meres_path):
                with open(meres_path, 'w', encoding='utf-8') as f:
                    f.write("Sheet_name;Meres\n")
            with open(meres_path, 'a', encoding='utf-8') as f:
                f.write(f"{sheet_name};\n")


            invalid_days = set(output_df['OPERATINGDAY'].dropna().unique()) - valid_operating_days
            if invalid_days:
                msg = f"⚠️ Μη έγκυρες τιμές OPERATINGDAY στο {base_name} - {sheet_name}: {sorted(invalid_days)}"
                print(msg)
                invalid_log_lines.append(msg)
            write_invalid_days_log(invalid_log_lines, timetable_dir)

#ΑΦΟΥ ΕΧΩ ΦΤΙΑΞΕΙ ΟΛΑ ΤΑ ΑΡΧΕΙΑ ΤΙΜΕΤΑΒΛΕ, ΤΑ ΕΝΩΝΩ ΣΕ ΕΝΑ
    all_dfs = []

    # Αναδρομική αναζήτηση όλων των αρχείων .csv
    for root, _, files in os.walk(timetable_dir):
        if 'meres' in root.lower():
            continue  # αγνόησε τον φάκελο meres
        for file in files:
            if file.endswith('.csv') and '_Timetable_' in file:
                file_path = os.path.join(root, file)
                try:
                    df = pd.read_csv(file_path, sep=';', dtype=str)
                    df['SOURCE_FILE'] = file  # optional: κρατά το αρχείο προέλευσης
                    all_dfs.append(df)
                except Exception as e:
                    print(f"⚠️ Σφάλμα στην ανάγνωση του {file_path}: {e}")

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        combined_output_path = 'output/combined_all_timetables.csv'
        os.makedirs(os.path.dirname(combined_output_path), exist_ok=True)
        combined_df.to_csv(combined_output_path, sep=';', index=False, encoding='utf-8')
        print(f"✅ Συνενώθηκαν {len(all_dfs)} αρχεία timetable → {combined_output_path}")
    else:
        print("⚠️ Δεν βρέθηκαν αρχεία timetable για συνένωση.")





# ====================================Blocks=================================
##διαγραφω αν υπαρχει τον φακελο timetable-output
def clean_blocks_dir():
    if os.path.exists(blocks_dir):
        shutil.rmtree(blocks_dir)
    os.makedirs(blocks_dir,exist_ok=True)

# def blocks():
#     print("▶ Δημιουργία Blocks...")
#     # read days_mapping and for each correct_depot , for each operacting ( of selected correct depot) create a file for block ( same logic as before) ->  (correct_depot + OPERATINGDAY + DayType).csv
#     # at the end we merge all csv into one for same correct_depot and Daytype
#
#     combined_output_path = 'output/combined_all_timetables.csv'
#     mapping_path = 'output/expanded_days_mapping.csv'
#     blocks_dir="blocks-output"
#     timetable_df = pd.read_csv(combined_output_path, sep=';', dtype=str)
#     mapping_df = pd.read_csv(mapping_path, sep=';', dtype=str)
#     os.makedirs(blocks_dir, exist_ok=True)
#
#
#     generated_files = []
#
#     # φιλτραρισμα
#     for _, row in mapping_df.iterrows():
#         depot = row['correct_depot']
#         op_day = row['OPERATINGDAY']
#         day_type = row['DayType']
#
#         """
#         subset = timetable_df[
#             (timetable_df['correct_depot'] == depot) &
#             (timetable_df['OPERATINGDAY'] == op_day)
#             ]
#         print(f"[DEBUG] {depot=} {op_day=} {day_type=} subset rows={len(subset)}")
#
#         if subset.empty:
#             print(f"⚠️ Δεν βρέθηκαν εγγραφές για {depot}, {op_day}, {day_type}")
#             continue
#         """
#         if ((timetable_df['correct_depot'] == depot) & (timetable_df['OPERATINGDAY'] == op_day)).any():
#
#             subset = timetable_df[
#                 (timetable_df['correct_depot'] == depot) &
#                 (timetable_df['OPERATINGDAY'] == op_day)
#                 ]
#             if not subset.empty:
#                 print ("is empty")
#
#             #print(subset.head())
#
#             #read days_mapping and for each correct_depot , for each operacting ( of selected correct depot) create a file for block ( same logic as before) ->  (correct_depot + OPERATINGDAY + DayType).csv
#             #at the end we merge all csv into one for same correct_depot and Daytype
#
#             # if not file.endswith('.csv'):
#             #     continue
#             # output_df = pd.read_csv(os.path.join(timetable_dir, file), sep=';', dtype=str)
#
#             #rint (subset['PASSAGEORDER'] == '1')
#
#
#             first = subset[subset['PASSAGEORDER'] == '1'].copy()
#             #print(first.head())
#             last = timetable_df[
#                 timetable_df.groupby('TRIPCODE')['PASSAGEORDER'].transform('max') == timetable_df['PASSAGEORDER']
#             ].copy()
#             #print(last.head())
#             print(f"[DEBUG] found {len(first)} πρώτες στάσεις και {len(last)} τελευταίες")
#
#             if first.empty or last.empty:
#                 print(f"⚠️ Παράλειψη: Δεν υπάρχουν αρκετές εγγραφές για {depot}, {op_day}, {day_type}")
#                 continue
#             merged2 = first.merge(
#                 last[['TRIPCODE','NODE','ARRIVALTIME']],
#                 on='TRIPCODE',
#                 suffixes=('_START','_END')
#             )
#             #print(merged2.head())
#
#             output2 = pd.DataFrame({
#                 'PROJUNIT_NAME':  day_type,
#                 'PROJECT_NAME':     depot,
#                 'VB_COMPANYCODE':   merged2['BLOCK'],
#                 'VEHBLOCK_ID':      merged2['BLOCK'],
#                 'PIECETYPE_NAME':   'Revenue',
#                 'LINE_COMPANYCODE': merged2['LINE'],
#                 'LINE_BASIN':       merged2['LINEBASIN'],
#                 'LINE_COMPANY':     'Def',
#                 'JOURNEY_ID':       merged2['TRIPCODE'],
#                 'TRIP_ID':          merged2['TRIPCODE'],
#                 'STARTNODE_COMPANYCODE': merged2['NODE_START'],
#                 'STARTNODE_BASIN':       'OSETH',
#                 'STARTNODE_COMPANY':     'Def',
#                 'ENDNODE_COMPANYCODE':   merged2['NODE_END'],
#                 'ENDNODE_BASIN':         'OSETH',
#                 'ENDNODE_COMPANY':       'Def',
#                 'START_TIME':            merged2['DEPARTURETIME'],
#                 'END_TIME':              merged2['ARRIVALTIME_END'],
#                 'RECHARGETYPE_NAME':     [None] * len(merged2),
#                 'DUTY':                  merged2['DUTY']
#             })
#             output2['VEHBLOCK_ID'] = output2['VEHBLOCK_ID'].apply(replace_if_contains_letter)
#
#             output2.sort_values(['VB_COMPANYCODE','START_TIME'], inplace=True)
#             #print(output2.head())
#
#             filename = f"{depot}_{op_day}_{day_type}_blocks.csv".replace(" ", "_")
#             filepath = os.path.join(blocks_dir, filename)
#             output2.to_csv(filepath, sep=';', index=False, encoding='utf-8')
#             generated_files.append(filename)
#             print(f"✅ Blocks αποθηκεύτηκαν στο {filename}")

def blocks_and_mergedDepotDaytype():
    print("▶ Δημιουργία Blocks...")
    # read days_mapping and for each correct_depot , for each operacting ( of selected correct depot) create a file for block ( same logic as before) ->  (correct_depot + OPERATINGDAY + DayType).csv
    # at the end we merge all csv into one for same correct_depot and Daytype

    combined_output_path = 'output/combined_all_timetables.csv'
    mapping_path = 'output/expanded_days_mapping.csv'
    blocks_dir = "blocks-output"
    timetable_df = pd.read_csv(combined_output_path, sep=';', dtype=str)
    mapping_df = pd.read_csv(mapping_path, sep=';', dtype=str)
    os.makedirs(blocks_dir, exist_ok=True)
    combined_dir = os.path.join(blocks_dir, 'combined')
    os.makedirs(combined_dir, exist_ok=True)

    # generated_files = []
    generated_files: list[tuple[str, str, str]] = []

    # φιλτραρισμα
    for _, row in mapping_df.iterrows():
        depot = row['correct_depot']
        op_day = row['OPERATINGDAY']
        day_type = row['DayType']

        """
        subset = timetable_df[
            (timetable_df['correct_depot'] == depot) &
            (timetable_df['OPERATINGDAY'] == op_day)
            ]
        print(f"[DEBUG] {depot=} {op_day=} {day_type=} subset rows={len(subset)}")

        if subset.empty:
            print(f"⚠️ Δεν βρέθηκαν εγγραφές για {depot}, {op_day}, {day_type}")
            continue
        """
        if ((timetable_df['correct_depot'] == depot) & (timetable_df['OPERATINGDAY'] == op_day)).any():

            subset = timetable_df[
                (timetable_df['correct_depot'] == depot) &
                (timetable_df['OPERATINGDAY'] == op_day)
                ]
            if not subset.empty:
                print("is empty")

            # print(subset.head())

            # read days_mapping and for each correct_depot , for each operacting ( of selected correct depot) create a file for block ( same logic as before) ->  (correct_depot + OPERATINGDAY + DayType).csv
            # at the end we merge all csv into one for same correct_depot and Daytype

            # if not file.endswith('.csv'):
            #     continue
            # output_df = pd.read_csv(os.path.join(timetable_dir, file), sep=';', dtype=str)

            # rint (subset['PASSAGEORDER'] == '1')

            first = subset[subset['PASSAGEORDER'] == '1'].copy()
            # print(first.head())
            last = timetable_df[
                timetable_df.groupby('TRIPCODE')['PASSAGEORDER'].transform('max') == timetable_df['PASSAGEORDER']
                ].copy()
            # print(last.head())
            print(f"[DEBUG] found {len(first)} πρώτες στάσεις και {len(last)} τελευταίες")

            if first.empty or last.empty:
                print(f"⚠️ Παράλειψη: Δεν υπάρχουν αρκετές εγγραφές για {depot}, {op_day}, {day_type}")
                continue
            merged2 = first.merge(
                last[['TRIPCODE', 'NODE', 'ARRIVALTIME']],
                on='TRIPCODE',
                suffixes=('_START', '_END')
            )
            # print(merged2.head())

            output2 = pd.DataFrame({
                'PROJUNIT_NAME': day_type,
                'PROJECT_NAME': depot,
                'VB_COMPANYCODE': merged2['BLOCK'],
                'VEHBLOCK_ID': merged2['BLOCK'],
                'PIECETYPE_NAME': 'Revenue',
                'LINE_COMPANYCODE': merged2['LINE'],
                'LINE_BASIN': merged2['LINEBASIN'],
                'LINE_COMPANY': 'Def',
                'JOURNEY_ID': merged2['TRIPCODE'],
                'TRIP_ID': merged2['TRIPCODE'],
                'STARTNODE_COMPANYCODE': merged2['NODE_START'],
                'STARTNODE_BASIN': 'OSETH',
                'STARTNODE_COMPANY': 'Def',
                'ENDNODE_COMPANYCODE': merged2['NODE_END'],
                'ENDNODE_BASIN': 'OSETH',
                'ENDNODE_COMPANY': 'Def',
                'START_TIME': merged2['DEPARTURETIME'],
                'END_TIME': merged2['ARRIVALTIME_END'],
                'RECHARGETYPE_NAME': [None] * len(merged2),
                'DUTY': merged2['DUTY']
            })
            output2['VEHBLOCK_ID'] = output2['VEHBLOCK_ID'].apply(replace_if_contains_letter)

            output2.sort_values(['VB_COMPANYCODE', 'START_TIME'], inplace=True)
            # print(output2.head())

            filename = f"{depot}_{op_day}_{day_type}_blocks.csv".replace(" ", "_")
            filepath = os.path.join(blocks_dir, filename)
            output2.to_csv(filepath, sep=';', index=False, encoding='utf-8')
            # generated_files.append(filename)
            generated_files.append((depot, day_type, filepath))

            print(f"✅ Blocks αποθηκεύτηκαν στο {filename}")

    """
        Για κάθε DayType που υπάρχει στα generated block αρχεία,
        διαβάζει όλα τα blocks-*.csv με αυτό το DayType και τα ενώνει
        σε ένα combined.csv.
        """

    # files = [f for f in os.listdir(blocks_dir) if f.endswith('_blocks.csv')]
    # groups = defaultdict(list)
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)

    for depot, day_type, path in generated_files:
        groups[(depot, day_type)].append(path)

    # για κάθε ομάδα, διαβάζουμε & concat
    for (depot, day_type), paths in groups.items():
        dfs = [pd.read_csv(p, sep=';', dtype=str) for p in paths]
        merged = pd.concat(dfs, ignore_index=True)

        out_name = f"{depot}_{day_type}_combined.csv".replace(" ", "_")
        out_path = os.path.join(combined_dir, out_name)
        merged.to_csv(out_path, sep=';', index=False, encoding='utf-8')
        print(f"✅ Merged {len(paths)} → {out_name}")




###################### Δημιουργία Duties CSV

        # ====================================Blocks=================================

def clean_duties_dir():
    if os.path.exists(duties_dir):
        # Πριν κάνεις cleanup στον φάκελο με shutil
        for handler in logging.root.handlers[:]:
            handler.close()
            logging.root.removeHandler(handler)
        shutil.rmtree(duties_dir)
    os.makedirs(duties_dir,exist_ok=True)

def setup_log():
    # Δημιουργία φακέλου log αν δεν υπάρχει
    log_dir = 'duties-output/final'
    os.makedirs(log_dir, exist_ok=True)
    # Δημιουργία μοναδικού ονόματος log με timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f'log_final_duties_{timestamp}.txt')
    # Καθαρισμός παλαιών handlers (αν έχεις ξανατρέξει logging.basicConfig)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    # Ρύθμιση logging μόνο σε αρχείο
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='utf-8'
    )


def duties():
    if not os.path.exists("blocks-output/combined"):
        os.mkdir("blocks-output/combined")
    combined_blocks_dir = "blocks-output/combined"
    duties_dir = "duties-output"
    os.makedirs(duties_dir, exist_ok=True)
    short_dir = os.path.join(duties_dir, 'short')
    os.makedirs(short_dir, exist_ok=True)
    print("▶ Δημιουργία Duties…")

    for file in os.listdir(combined_blocks_dir):
        if not file.endswith('_combined.csv'):
            continue
        # output3 = pd.read_csv(os.path.join(blocks_dir, file), sep=';', dtype=str)

        base = file[:-len("_combined.csv")]
        blocks_fp = os.path.join(combined_blocks_dir, file)
        df_blocks = pd.read_csv(blocks_fp, sep=';', dtype=str)

        df_duties = pd.DataFrame({
            'VERSION': "VERSION_U",
            'PROJECT_NAME': df_blocks['PROJECT_NAME'],
            'PROJUNIT_NAME': df_blocks['PROJUNIT_NAME'],
            'DUTY_COMPANYCODE': df_blocks['DUTY'],
            'DUTY_ID': df_blocks['JOURNEY_ID'],
            'PIECETYPE_NAME': 'VB_Piece',
            'REFERREDVB_COMPANYCODE': df_blocks['VB_COMPANYCODE'],
            'PRETIMESEC': [None] * len(df_blocks),
            'POSTTIMESEC': [None] * len(df_blocks),
            'STARTNODE_COMPANYCODE': df_blocks['STARTNODE_COMPANYCODE'],
            'STARTNODE_BASIN': 'OSETH',
            'STARTNODE_COMPANY': 'Def',
            'ENDNODE_COMPANYCODE': df_blocks['ENDNODE_COMPANYCODE'],
            'ENDNODE_BASIN': 'OSETH',
            'ENDNODE_COMPANY': 'Def',
            'START_TIME': df_blocks['START_TIME'],
            'END_TIME': df_blocks['END_TIME']
        })

        df_duties.sort_values(['DUTY_COMPANYCODE', 'START_TIME'], inplace=True)
        duties_filename = f"{base}_Duties_.csv"
        duties_path = os.path.join(duties_dir, duties_filename)
        df_duties.to_csv(duties_path, index=False, sep=';', encoding='utf-8')
        print(f"   • Saved {duties_filename}")

        # ----- Εφαρμογή shortDuty logic (ενσωματωμένο) -----

        #  Ανάθεση DUTY_ID
        df_done = pd.read_csv(duties_path, sep=';', dtype=str)
        df_done = assign_duty_ids(df_done)
        # Μετατροπη short
        df_short = make_short_duty(df_done)

        #  Εξαγωγή νέου CSV με πρόθεμα 'short_'
        # done_name = f"done{duties_filename}"
        # done_path = os.path.join(duties_dir, done_name)
        # df_done.to_csv(done_path, index=False, sep=';', encoding='utf-8')
        # print(f"   Done Duties (με DUTY_ID) saved to: {done_path}")

        short_name = f"short_{duties_filename}"
        short_path = os.path.join(short_dir, short_name)
        df_short.to_csv(short_path, index=False, sep=';', encoding='utf-8')
        print(f"  Short Duties (με DUTY_ID) saved to: {short_path}")

    print(f" ✔ Ολοκληρώθηκε:")



def final_duties():
    short_dir = 'duties-output/short'
    final_dir = 'duties-output/final'
    os.makedirs(final_dir, exist_ok=True)
    deadhead_path = 'static/Vehicle_block_deadheads.csv'
    deadhead_df = pd.read_csv(deadhead_path, sep=';', dtype=str)
    mapping_path = 'static/mappings.txt'
    mapping_df = pd.read_csv(mapping_path, sep=';', dtype=str)
    mapping_dict = dict(zip(mapping_df['depot'], mapping_df['mapping']))



    for file in os.listdir(short_dir):
        if not file.endswith('.csv'):
            continue

        short_df = pd.read_csv(os.path.join(short_dir, file), sep=';', dtype=str)
        final_rows = []



        group_keys = ['REFERREDVB_COMPANYCODE', 'PROJECT_NAME', 'PROJUNIT_NAME']
        for (vb_code, project_name, projunit_name), group in short_df.groupby(group_keys):
            group = group.copy()
            if len(group) != 2:
                logging.warning(f"⚠️ Παράλειψη {vb_code} στο {file} (δεν έχει 2 γραμμές)")
                #final_rows.extend(group.to_dict(orient='records'))
                continue

            deadhead_matches = deadhead_df[
                (deadhead_df['VB_COMPANYCODE'] == vb_code) &
                (deadhead_df['PROJECT_NAME'] == project_name) &
                (deadhead_df['PROJUNIT_NAME'] == projunit_name)
                ]
            if deadhead_matches.empty:
                logging.warning(f"⚠️ Παράλειψη {vb_code} στο {file} (δεν βρέθηκε deadhead)")
                continue

            first_row = group.iloc[0].copy()
            last_row = group.iloc[1].copy()

            start_time = deadhead_matches['START_TIME'].iloc[0]
            end_time = deadhead_matches['END_TIME'].iloc[-1]

            first_row['START_TIME'] = start_time
            first_row['STARTNODE_COMPANYCODE'] = project_name
            final_rows.append(first_row)

            third_row = last_row.copy()
            third_row['END_TIME'] = end_time
            third_row['ENDNODE_COMPANYCODE'] = project_name

            middle_row = last_row.copy()
            middle_row['PIECETYPE_NAME'] = "Pre_Duty"
            #middle_row['REFERREDVB_COMPANYCODE'] = ''

            depot_node = third_row['STARTNODE_COMPANYCODE']
            middle_row['STARTNODE_COMPANYCODE'] = depot_node
            middle_row['ENDNODE_COMPANYCODE'] = depot_node

            try:
                third_start_time = datetime.strptime(third_row['START_TIME'], "%H:%M:%S")
                middle_row['START_TIME'] = (third_start_time - timedelta(minutes=10)).strftime("%H:%M:%S")
                middle_row['END_TIME'] = third_start_time.strftime("%H:%M:%S")
            except Exception as e:
                logging.warning(f"⚠️ Σφάλμα parsing ώρας για {vb_code} στο {file}: {e}")
                continue

            final_rows.extend([middle_row, third_row])

        if final_rows:
            result_df = pd.DataFrame(final_rows)

            #for REFERREDVB_COMPANYCODE_id, group in result_df.groupby('REFERREDVB_COMPANYCODE'):
            for (vb_code, project_name, projunit_name), group in result_df.groupby(group_keys):

                if len(group) == 3:
                    start_node = group.iloc[0]['STARTNODE_COMPANYCODE']
                    end_node = group.iloc[-1]['ENDNODE_COMPANYCODE']


                    if start_node in mapping_dict:
                        result_df.at[group.index[0], 'STARTNODE_BASIN'] = mapping_dict[start_node]
                    else:
                        logging.warning(f"🔍 Δεν βρέθηκε mapping για START: {start_node}")

                    if end_node in mapping_dict:
                        result_df.at[group.index[-1], 'ENDNODE_BASIN'] = mapping_dict[end_node]
                    else:
                        logging.warning(f"🔍 Δεν βρέθηκε mapping για END: {end_node}")


            # Διαγραφή REFERREDVB_COMPANYCODE στη Pre_Duty γραμμή
            result_df.loc[result_df['PIECETYPE_NAME'] == 'Pre_Duty', 'REFERREDVB_COMPANYCODE'] = ''

            output_path = os.path.join(final_dir, f"final_{file}")
            result_df.to_csv(output_path, sep=';', index=False, encoding='utf-8')
            print(f"✅ Final Duties αποθηκεύτηκαν στο: {output_path}")


# ------------------- Ενημέρωση ιστορικών αρχείων ------------------------
if final:
    with open(trip_history_file, 'w') as f:
        for uid in sorted(used_trip_ids):
            f.write(uid + '\n')

    with open(duty_history_file, 'w') as f:
        for uid in sorted(used_duty_ids):
            f.write(uid + '\n')

    print("✅ Το history/used_*.txt έχει ενημερωθεί με όλα τα IDs που δημιουργήθηκαν.")
    print(f"Εγγραφές του trip_history είναι: {len(used_trip_ids)}")
    print(f"Εγγραφές του used_duty_ids είναι: {len(used_duty_ids)}")
else:
    print("Οχι αλλαγές στα history")




#==========================================meres-diadika apo combined timetable====================================


def create_days_mapping_file(combined_csv_path: str, output_txt_path: str) -> None:
    try:
        df = pd.read_csv(combined_csv_path, sep=';', dtype=str)

        result = df[['correct_depot', 'OPERATINGDAY']].drop_duplicates()


        result = result.sort_values('correct_depot')

        result['DayType'] = None

        result.to_csv(output_txt_path, sep=';', index=False, encoding='utf-8')


        print(f"✅ Δημιουργήθηκε αρχείο mapping: {output_txt_path}")
    except Exception as e:
        print(f"❌ Σφάλμα κατά τη δημιουργία days mapping αρχείου: {e}")





def update_days_mapping_from_static(mapping_txt_path, static_csv_path):
    try:
        # Φόρτωση και των δύο αρχείων

        mapping_df = pd.read_csv(mapping_txt_path, sep=';', dtype=str)
        static_df = pd.read_csv(static_csv_path, sep=';', dtype=str)


        # Καθαρίζουμε τα κείμενα
        #mapping_df['DAYS'] = mapping_df['DAYS'].str.strip()
        #static_df['Operating_Days'] = static_df['Operating_Days'].str.strip()
        #static_df['Days_Diadiko'] = static_df['Days_Diadiko'].str.strip()

        # # Κάνουμε merge με βάση DAYS <-> Operating_Days
        # merged = mapping_df.merge(
        #     static_df[['Operating_Days', 'Day_Map','Days_Diadiko']],
        #     on ='Operating_Days',
        #     left_index=False,
        #     how='left'
        # )
        # #print(merged.head())

        merged = mapping_df.merge(
            static_df[['Operating_Days', 'Day_Map']],
            right_on='Operating_Days',
            left_on='OPERATINGDAY',
            how='left'
        )
        # Τελικές στήλες για αποθήκευση
        merged = merged[['correct_depot', 'OPERATINGDAY', 'Day_Map']]

        merged["Day_Map"]=None

        # Αντικαθιστούμε τη στήλη

        #merged['DAYSDIADIKO'] = merged['Days_Diadiko']
        #final_df = merged[['Day_Map', 'DAYSDIADIKO']]
        #print(final_df.head())

        # Αποθήκευση
        merged.to_csv(mapping_txt_path, sep=';', index=False, encoding='utf-8')
        print(f"✅ Ενημερώθηκε το αρχείο: {mapping_txt_path}")

    except Exception as e:
        print(f"❌ Σφάλμα κατά την ενημέρωση days mapping: {e}")





#isos vale auto san sinartis gia elegxo kathimerinon
def write_invalid_days_log(invalid_log_lines, output_dir):
    """
    Αποθηκεύει τις μη έγκυρες τιμές OPERATINGDAY σε αρχείο txt.
    """
    if not invalid_log_lines:
        return

    log_file_path = os.path.join(output_dir, "invalid_operating_days_log.txt")
    with open(log_file_path, 'w', encoding='utf-8') as f:
        for line in invalid_log_lines:
            if isinstance(line, str) and line.strip():
                f.write(line + '\n')

    print(f"📄 Καταγράφηκαν {len(invalid_log_lines)} μη έγκυρες εγγραφές στο {log_file_path}")



def create_depot_timetables(combined_output_path):
    timetable = pd.read_csv(combined_output_path, sep=';', dtype=str)
    patternsA_df = pd.read_csv('static/PatternAttributes.csv', sep=';', dtype=str)
    depots = pd.read_csv("static/DEPOTS.txt", sep=';', dtype=str)

    #print(patternsA_df.head())
    #print(patternsA_df.columns.tolist())
    #print(depots.head())

    # Merge the dataframes on PATTERNCODE
    # This will bring the DEPOT column from patternsA_df into timetable
    timetable = timetable.merge(
        patternsA_df[['PATTERNCODE', 'Depot']],
        how='left',
        right_on='PATTERNCODE',
        left_on='PATTERN'
    )

    #print(timetable.head())

    timetable = timetable.merge(
        depots[['wrong_depot','correct_depot']],
        how='left',
        right_on='wrong_depot',
        left_on='Depot'
    )

    # Assign Depot to ProjectDepot
    #timetable['ProjectDepot'] = timetable['Depot']

    #drop Depot collumn
    timetable = timetable.drop(columns=['Depot'])
    timetable = timetable.drop(columns=['wrong_depot'])

    timetable.to_csv("output/combined_all_timetables.csv", sep=';', index=False, encoding='utf-8')


def after_insert_day_type():
    combined_csv_path = 'output/combined_all_timetables.csv',
    day_maps= "output/days_mapping.txt"
    day_maps = pd.read_csv(day_maps, sep=';', dtype=str)



    # Convert the Day_Map column from string to list
    day_maps['DayType'] = day_maps['DayType'].apply(
        lambda x: ast.literal_eval("[" + ",".join(f'"{i.strip()}"' for i in x.strip("[]").split(",")) + "]")
    )

    # Explode the list into multiple rows
    result = day_maps.explode('DayType')

    # Optional: reset index
    result = result.reset_index(drop=True)

    print(result)
    result.to_csv('output/expanded_days_mapping.csv', sep=';', index=False, encoding='utf-8')


# === Κλήση κύριου προγράμματος ===
if __name__ == '__main__':


    #clean_timetable_dir()
    #timetable_and_combine()



    #-----createdepot sthlh telos timetable.csv apo patternAttributes
    #create_depot_timetables(combined_output_path='output/combined_all_timetables.csv')




    #create_days_mapping_file( combined_csv_path='output/combined_all_timetables.csv',output_txt_path='output/days_mapping.txt')


    #-----------------------------------------------------------------------------------------------------------------------------------------------------


    #-----auto meta to maior kai daytype------#
    #after_insert_day_type()


    #update_days_mapping_from_static(mapping_txt_path='output/days_mapping.txt',static_csv_path='static/Operating_Days.csv')

    #clean_blocks_dir()
    #blocks_and_mergedDepotDaytype()

    clean_duties_dir()
    setup_log()
    duties()
    final_duties()



