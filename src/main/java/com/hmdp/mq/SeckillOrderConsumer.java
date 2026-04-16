package com.hmdp.mq;

import com.hmdp.entity.VoucherOrder;
import com.hmdp.service.IVoucherOrderService;
import org.apache.rocketmq.client.consumer.DefaultMQPushConsumer;
import org.apache.rocketmq.common.consumer.ConsumeFromWhere;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.spring.annotation.MessageModel;
import org.apache.rocketmq.spring.annotation.RocketMQMessageListener;
import org.apache.rocketmq.spring.core.RocketMQPushConsumerLifecycleListener;
import org.apache.rocketmq.spring.core.RocketMQListener;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

@Slf4j
@Component
@RocketMQMessageListener(
        topic = SeckillOrderProducer.SECKILL_ORDER_TOPIC,
        consumerGroup = "seckill-order-consumer-group",
        messageModel = MessageModel.CLUSTERING
)
public class SeckillOrderConsumer implements RocketMQListener<VoucherOrder>, RocketMQPushConsumerLifecycleListener {

    @Resource
    private IVoucherOrderService voucherOrderService;

    @Override
    public void onMessage(VoucherOrder voucherOrder) {
        if (voucherOrderService.getById(voucherOrder.getId()) != null) {
            log.info("检测到重复投递，orderId={}，直接确认消息", voucherOrder.getId());
            return;
        }
        log.debug("收到秒杀订单消息，orderId={}, userId={}, voucherId={}",
                voucherOrder.getId(), voucherOrder.getUserId(), voucherOrder.getVoucherId());
        voucherOrderService.createVoucherOrder(voucherOrder);
    }

    @Override
    public void prepareStart(DefaultMQPushConsumer consumer) {
        consumer.setConsumeFromWhere(ConsumeFromWhere.CONSUME_FROM_FIRST_OFFSET);
    }
}
