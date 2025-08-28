TODO

ΕΚΤΕΛΕΣΗ MAIN
ΥΠΆΡΧΟΥΝ ΤΡΕΙΣ ΦΑΣΕΙΣ ΠΑΡΑΓΩΓΗΣ ΑΡΧΕΙΩΝ TIMETABLE, BLOCK, DUTIES 
Ανάλογα την φάση σχολιάζεται το ανίστοιχo κομμάτι κώδικα.

A)TIMETABLE
- clean_timetable_dir()
Διαγράφει τον φάκελο timetable-output
- Ο χρηστης κατεβάζει στον φάκελο static τα τελευταια ενημερωμένα pattern & patternAttribute αρχεια απο Maior
- timetable_and_combine()
  timestamp = datetime.now().strftime('%Y%m%d_%H%M')
  combined_output_path = f'output/{timestamp}_combined_all_timetables.csv'
  create_depot_timetables(combined_output_path)
Παραγεται το αρχειο Timetable με timestamp στο ονομά του. Ο χρήστης μετατρέπει το όνομα του αρχείου σε combined_all_timetables.csv
- create_days_mapping_file (combined_csv_path='output/combined_all_timetables.csv',output_txt_path='output/days_mapping.txt')
Φτιαχνει days_mapping.txt με στηλες correct_depot;OPERATINGDAY;DayType(κενη)
- update_days_mapping_from_static (mapping_txt_path='output/days_mapping.txt',static_csv_path='static/Operating_Days.csv')
Προσθετει τη στηλη Day_Map στο days_mapping.txt. Ο χρηστης τωρα περνάει τις τιμές στην στηλη DayType από Maior.
- after_insert_day_type() Δημιουργεί πολλαπλές γραμμές ανά DayType

B)BLOCKS
- validate timetables Maior
- clean_blocks_dir()
Διαγράφει τον φάκελο blocks-output
- combined_output_path = 'output/20250730_1333_combined_all_timetables.csv'
  blocks_and_mergedDepotDaytype(combined_output_path)
Δημιουργούνται στον φάκελο blocks-output/combined/ τα ζητούμενα αρχεία

C)DUTIES
- validate blocks Maior
- Ο χρηστης κατεβάζει στον φάκελο απο Maior static shift->export vehicle blocks-> και μετονομαζει αρχειο σε static/Vehicle_block_deadheads.csv 
- timetable_and_combine()
- clean_duties_dir()
  setup_log()
Διαγράφει τον φάκελο duties-output 
- duties()
  final_duties()
Δημιουργούνται στον φάκελο duties-output/final/ τα ζητούμενα αρχεία







TODO_LOGS
1. να βλεπει στoν φακελο timetable-output (ονομα στηλης?)operatingday και να ελεγχει αν αυτο υπάρχει στο αρχείο Operating_days.csv(το εφτιαξε ο δημητρης και ισως χρειαστει να γίνει ξανα έλεγχος).
2. DES πως θα παιρνει στα Blocks Το timestamp-combine_all_timetables και οχι το μετονομασμένο.
3. μηπως πρεπει να σβηνω και τον φακελο output?
4. το μετονομασμενο all_timetables χρησιμοποιειται κυριως στα daymapping






- def create_days_mapping_file():
  output/combined_all_timetables.csv -> output/days_mapping.txt
Εξάγει μοναδικούς συνδυασμούς correct_depot & OPERATINGDAY με κενό DayType. Χρησιμεύει ως αρχικό αρχείο αντιστοίχισης για τις μέρες λειτουργίας.

- def update_days_mapping_from_static():
  output/days_mapping.txt και static/Operating_Days.csv -> (τροποποιεί) output/days_mapping.txt
Συμπληρώνει το αρχείο mapping με τις αντίστοιχες εγγραφές Day_Map με βάση πίνακα static δεδομένων.

- write_invalid_days_log():
  δημιουργειται αρχειο στον timetable-output μονο αν υπαρχουν αναντιστοιχίες.
  Καταγράφει ποιες τιμές OPERATINGDAY δεν βρέθηκαν στο Operating_Days.csv. Χρησιμοποιείται για debugging.
  χρησιμοποιειται μεσα στην timetable, δες το καλυτερα.

- create_depot_timetables():
  output/combined_all_timetables.csv, static/PatternAttributes.csv, static/DEPOTS.txt -> output/{timestamp}_combined_all_timetables.csv με στήλη correct_depot
Εμπλουτίζει το αρχείο timetables με τη σωστή πληροφορία για το depot κάθε γραμμής μέσω mapping.

- after_insert_day_type(): 
output/days_mapping.txt -> output/expanded_days_mapping.csv
Επεξεργάζεται πολλαπλά DayTypes (σε λίστα) για κάθε depot/μέρα. Δημιουργεί πολλαπλές γραμμές ανά DayType για χρήση στα blocks.













 def check_pattern_line_consistency(
     excel_csv_path='output/combined_all_timetables.csv',
     pattern_attributes_path='static/PatternAttributes.csv',
     log_output_path='output/line_consistency_log.txt'
 ):
     """
     Ελέγχει αν τα PATTERNs που εμφανίζονται στο Excel έχουν:
     1. Αντιστοίχιση στο PatternAttributes.csv
     2. Την ίδια τιμή LINE

     Δημιουργεί log αρχείο με όποιες ασυνέπειες εντοπιστούν.
     """

     try:
         # Φόρτωση αρχείων
         excel_df = pd.read_csv(excel_csv_path, sep=';', dtype=str)
         pattern_attrs = pd.read_csv(pattern_attributes_path, sep=';', dtype=str)

         # Καθαρισμός και προετοιμασία
         excel_patterns = excel_df[['PATTERN', 'LINE']].dropna().drop_duplicates()
         pattern_attrs = pattern_attrs[['PATTERNCODE', 'LINE']].dropna().drop_duplicates()
         pattern_attrs = pattern_attrs.rename(columns={'PATTERNCODE': 'PATTERN', 'LINE': 'STATIC_LINE'})

         # Merge PATTERNs
         merged = excel_patterns.merge(pattern_attrs, on='PATTERN', how='left')

         # Αρχικοποίηση λίστας log
         log_lines = []

         # 1. Λείποντα PATTERNs
         missing_patterns = merged[merged['STATIC_LINE'].isna()]
         for _, row in missing_patterns.iterrows():
             log_lines.append(
                 f"❌ PATTERN {row['PATTERN']} με LINE={row['LINE']} στο Excel ΔΕΝ βρέθηκε στο PatternAttributes.csv"
             )

         # 2. Ασυμφωνία LINE
         mismatch_patterns = merged[
             (~merged['STATIC_LINE'].isna()) &
             (merged['LINE'] != merged['STATIC_LINE'])
         ]
         for _, row in mismatch_patterns.iterrows():
             log_lines.append(
                 f"🔍 PATTERN {row['PATTERN']}: Στο Excel LINE={row['LINE']}, αλλά στο PatternAttributes.csv LINE={row['STATIC_LINE']} ❗"
             )

         # Δημιουργία φακέλου output αν δεν υπάρχει
         os.makedirs(os.path.dirname(log_output_path), exist_ok=True)

         # Αποθήκευση αρχείου log
         with open(log_output_path, 'w', encoding='utf-8') as f:
             for line in log_lines:
                 f.write(line + '\n')

         print(f"✅ Ολοκληρώθηκε έλεγχος. Καταγράφηκαν {len(log_lines)} περιπτώσεις στο {log_output_path}")

     except Exception as e:
         print(f"❌ Σφάλμα στον έλεγχο consistency: {e}")








def assign_times(group):
                 try:
                     dep_time_str = input_df.loc[group['MERGE_KEY'].iloc[0], 'ΑΝΑΧΩΡΗΣΗ']
                     arr_time_str = input_df.loc[group['MERGE_KEY'].iloc[0], 'ΤΕΡΜΑ']
            
                     dep_time = parse_extended_time(dep_time_str)
                     arr_time = parse_extended_time(arr_time_str)
            
                     if pd.isna(dep_time) or pd.isna(arr_time):
                         return group  # Αν δεν υπάρχουν, μην κάνεις τίποτα
            
                     n = len(group)
                     total_duration = (arr_time - dep_time).total_seconds()
            
                     for i, idx in enumerate(group.index):
                         t = dep_time + timedelta(seconds=(i / (n - 1)) * total_duration)
                         time_str = t.strftime('%H:%M:%S')
                         group.at[idx, 'ARRIVALTIME'] = time_str
                         group.at[idx, 'DEPARTURETIME'] = time_str
            
                 except Exception as e:
                     print(f"Σφάλμα στην ώρα για MERGE_KEY={group['MERGE_KEY'].iloc[0]}: {e}")
            
                 return group


