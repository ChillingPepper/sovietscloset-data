import time

from changelog import update_changelog
from oopsies import update_oopsies
from sovietscloset import SovietsCloset
from update import update_data

if __name__ == "__main__":
    old_sovietscloset = SovietsCloset()

    updated = False
    while not updated:
        try:
            update_data()
            updated = True
        except:
            print("something went wrong updating the data")
            sleep_minutes = 5
            print(f"trying again in {sleep_minutes} minutes")
            time.sleep(sleep_minutes * 60)
            print("trying again now")

    new_sovietscloset = SovietsCloset()
    update_changelog(old_sovietscloset, new_sovietscloset)

    update_oopsies()
