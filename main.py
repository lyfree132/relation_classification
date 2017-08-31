# -*- encoding: utf-8 -*-
# Created by han on 17-7-8

import os
import cPickle
from datetime import datetime
from data_loader import DataLoader
from model_settings import *
from models import *
from evaluate import *

ms_dict = {
    'cnn': CnnSetting,
    'gru': RnnSetting,
    'bigru': RnnSetting,
    'bigru_att': RnnSetting,
    'bigru_selfatt': RnnSetting,
    'bigru_att_mi': RnnMiSetting
}

m_dict = {
    'cnn': Cnn,
    'gru': Gru,
    'bigru': BiGru,
    'bigru_att': BiGru_Att,
    'bigru_selfatt': BiGru_SelfAtt,
    'bigru_att_mi': BiGru_Mi
}


def get_ids(c_feature):
    """
    get index of word, character and relation
    :param c_feature: if c_feature is true, use character level features
    :return:
    """
    if c_feature:
        with open('./data/id2char.pkl', 'rb') as f:
            id2x = cPickle.load(f)
        with open('./data/char2id.pkl', 'rb') as f:
            x2id = cPickle.load(f)
    else:
        with open('./data/id2word.pkl', 'rb') as f:
            id2x = cPickle.load(f)
        with open('./data/word2id.pkl', 'rb') as f:
            x2id = cPickle.load(f)
    with open('./origin_data/idx2rel.pkl', 'rb') as f:
        id2rel = cPickle.load(f)

    return x2id, id2x, id2rel


def main():
    """
    initialize, train and evaluate models
    """
    model_name = 'gru'

    # feature select
    c_feature = True

    # train and test parameters
    train_epochs_num = 100
    batch_size = 512

    # get indexes
    x2id, id2x, id2rel = get_ids(c_feature)

    # result saving path
    res_path = os.path.join('./result', model_name, '{}_{}'.format(model_name, 'c' if c_feature else 'w'))
    if not os.path.exists(res_path):
        os.makedirs(res_path)
    res_prf = os.path.join(res_path, 'prf.txt')
    res_ana = os.path.join(res_path, 'analysis.txt')
    log_prf = tf.gfile.GFile(res_prf, mode='a')
    log_ana = tf.gfile.GFile(res_ana, mode='a')

    # basic model setting
    model_setting = ms_dict[model_name]()

    # initialize data loader
    print 'data loader initializing...'
    mult_ins = True if '_mi' in model_name else False

    if 'cnn' in model_name:
        data_loader = DataLoader(
            './data', c_feature=c_feature, multi_ins=mult_ins, cnn_win_size=model_setting.win_size
        )
    else:
        data_loader = DataLoader('./data', c_feature=c_feature, multi_ins=mult_ins)

    # update max sentence length
    model_setting.sen_len = data_loader.max_sen_len

    # initialize model
    model = m_dict[model_name](data_loader.embedding, model_setting)

    with tf.Session() as session:
        tf.global_variables_initializer().run()
        saver = tf.train.Saver(max_to_keep=None)
        # best evaluation f1
        best_test_f1 = 0
        for epoch_num in range(train_epochs_num):
            # training
            iter_num = 0
            batches = data_loader.get_train_batches(batch_size=batch_size)
            for batch in batches:
                iter_num += 1
                loss = model.fit(session, batch, dropout_keep_rate=model_setting.dropout_rate)
                _, c_label, _ = model.evaluate(session, batch)
                if iter_num % 100 == 0:
                    _, prf_macro, _ = get_p_r_f1(c_label, batch.y)
                    p, r, f1 = prf_macro
                    log_info = 'train: ' + str(datetime.now()) + ' epoch: {:>3}, batch: {:>4}, lost: {:.3f},' \
                                                                 ' p: {:.3f}%, r: {:.3f}%, f1:{:.3f}%\n'.format(
                        epoch_num, iter_num, loss, p * 100, r * 100, f1 * 100
                    )
                    log_prf.write(log_info)
                    print 'train: ', datetime.now(), ' epoch: {:>3}, batch: {:>4}, lost: {:.3f}, p: {:.3f}%,' \
                                                     ' r: {:.3f}%, f1:{:.3f}%'.format(
                        epoch_num, iter_num, loss, p * 100, r * 100, f1 * 100
                    )

            # evaluate after each epoch
            use_neg = True
            test_batches = data_loader.get_test_batches(batch_size)
            test_loss, test_prob, test_pred, test_ans = [], [], [], []
            test_x, test_p1, test_p2 = [], [], []
            for batch in test_batches:
                batch_loss, batch_pred, batch_prob = model.evaluate(session, batch)
                test_loss.append(batch_loss)
                test_prob += list(batch_prob)
                test_pred += list(batch_pred)
                test_ans += list(batch.y)
                test_x += list(batch.x)
                test_p1 += list(batch.pos1[:, 0])
                test_p2 += list(batch.pos2[:, 0])
            test_loss = np.mean(test_loss)
            prf_list, prf_macro, prf_micro = get_p_r_f1(test_pred, test_ans, use_neg)
            p, r, f1 = prf_macro
            log_info = 'test : ' + str(datetime.now()) + ' epoch: {:>3}, lost: {:.3f}, p: {:.3f}%, r: {:.3f}%,' \
                                                        ' f1:{:.3f}%\n'.format(
                epoch_num, test_loss, p * 100, r * 100, f1 * 100
            )

            # best performance
            if f1 > best_test_f1:
                best_test_f1 = f1
                # record p, r, f1
                log_ana.write(log_info)
                if use_neg:
                    for idx in range(len(prf_list)):
                        rel_prf = 'rel: {:>2}_{:<6}, p: {:.3f}%, r: {:.3f}%, f1:{:.3f}%\n'.format(
                            idx, id2rel[idx], prf_list[idx][3] * 100, prf_list[idx][4] * 100, prf_list[idx][5] * 100
                        )
                        log_ana.write(rel_prf)
                else:
                    for idx in range(len(prf_list)):
                        rel_prf = 'rel: {}_{}, p: {:.3f}%, r: {:.3f}%, f1:{:.3f}%\n'.format(
                            idx+1, id2rel[idx+1],
                            prf_list[idx][3] * 100, prf_list[idx][4] * 100, prf_list[idx][5] * 100
                        )
                        log_ana.write(rel_prf)

                # record wrong instance multi-instance do no support this process
                if not mult_ins:
                    wrong_ins = get_wrong_ins(
                        test_pred, test_ans, test_x, test_p1, test_p2, x2id, id2x, id2rel, use_neg
                    )
                    wrong_ins = sorted(wrong_ins, key=lambda x: x[1])
                    wrong_ins = ['\t'.join(i) + '\n' for i in wrong_ins]
                    for ins in wrong_ins:
                        log_ana.write(ins)
                log_ana.write('-' * 80 + '\n')

                # draw pr curve
                # prc_fn = os.path.join(res_path, 'prc_epoch{}.png'.format(epoch_num))
                # save_prcurve(test_prob, test_ans, model_name, prc_fn)

                # save model
                saver.save(session, os.path.join(res_path, 'model_saved'), epoch_num)

            log_prf.write(log_info)
            print 'test : ', datetime.now(), 'epoch: {:>3}, lost: {:.3f}, p: {:.3f}%, r: {:.3f}%, f1:{:.3f}%'.format(
                epoch_num, test_loss, p * 100, r * 100, f1 * 100
            )

if __name__ == '__main__':
    main()
