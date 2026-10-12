Synthetic test data for the Import Clearance Document Checker
All names, numbers and companies are invented. Not real shipments.

setNN/setNN_invoice.pdf          commercial invoice
setNN/setNN_packing_list.pdf     packing list
setNN/setNN_bill_of_lading.pdf   bill of lading
setNN/setNN_expected.json        what the extractor should return (schema version 1),
                                 the expected findings, and the expected result of each check
answer_key.json                  the key for all ten sets in one file

Sets 1 to 3 are clean (no findings expected). Sets 4 to 10 each contain one planted error.
Layout A: sets 1, 3, 4, 5, 10. Layout B: sets 2, 6, 7, 8, 9.
Put this folder in the test-data folder of the repository.
