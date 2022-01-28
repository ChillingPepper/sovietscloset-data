import time

from changelog import update_changelog
from oopsies import update_oopsies
from sovietscloset import SovietsCloset
from update import update_data

if __name__ == "__main__":
    old_sovietscloset = SovietsCloset()

    try:
        update_data()
    except:
        print("something went wrong updating the data")
        sleep_minutes = 5
        for i in range(sleep_minutes):
            print(f"trying again in {sleep_minutes - i} minutes")
            time.sleep(60)
        print("trying again now")
        update_data()

    new_sovietscloset = SovietsCloset()
    update_changelog(old_sovietscloset, new_sovietscloset)

    update_oopsies()
