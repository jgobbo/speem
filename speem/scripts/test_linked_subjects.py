from daquiri.ui.lens import LensSubject


if __name__ == "__main__":
    print("Starting")
    subj = LensSubject((1, 2))
    lens = subj.view_index(0)
    lens2 = subj.view_index(1)

    subj.subscribe(print)
    lens.subscribe(print)
    lens2.subscribe(print)

    subj.on_next((2, 3))
    lens.on_next(4)
    lens.on_next(5)

    print("!!")

    subj2 = LensSubject((1, 2))
    subj2.subscribe(print)
    id2 = subj2.id()
    id2.subscribe(print)

    id2.on_next((3, 4))
    subj2.on_next((7, 8))