import time

from changelog import update_changelog
from oopsies import update_oopsies
from sovietscloset import SovietsCloset
from update import update_data

if __name__ == "__main__":
    try:
        old_sovietscloset = SovietsCloset()
        update_data()
        new_sovietscloset = SovietsCloset()

        update_changelog(old_sovietscloset, new_sovietscloset)

        update_oopsies()

    except:
        print("something went wrong, try again later")
