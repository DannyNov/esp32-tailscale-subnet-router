int main(void)
{
    const int sizes[] = {64, 1240, 1500};
    const int offers[] = {127, 128, 129, 256};
    unsigned epochs = 0;

    for (unsigned size = 0; size < sizeof sizes / sizeof sizes[0]; size++) {
        const int length = sizes[size];
        for (unsigned group = 0; group < sizeof offers / sizeof offers[0]; group++) {
            const int offered = offers[group];
            const int capacity = offered < 128 ? offered : 128;
            for (int epoch = 0; epoch < 20; epoch++) {
                unsigned char packet[1500] = {4};
                reset();
                for (int id = 0; id < offered; id++) {
                    packet[4] = (unsigned char)id;
                    assert(offer(packet, length, id) == (id < capacity));
                }
                assert(depth() == capacity);
                assert(freed() == offered - capacity);
                for (int id = 0; id < capacity; id++) {
                    assert(take(packet, length));
                    assert(packet[4] == id);
                }
                assert(!take(packet, length));
                assert(depth() == 0);
                assert(freed() == offered);
                epochs++;
            }
        }
    }
    assert(epochs == 240);
    puts("PASS 240 queue epochs");
    return 0;
}
